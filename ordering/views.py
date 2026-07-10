import json
from decimal import Decimal
from django.db import models
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.urls import reverse_lazy

from .models import Category, MenuItem, Order, OrderItem

class MenuView(View):
    def get(self, request):
        # Optimized menu query retrieving categories and their available items in 1 sweep
        categories = Category.objects.prefetch_related(
            models.Prefetch('items', queryset=MenuItem.objects.filter(is_available=True))
        ).all()
        
        # Pull any existing items in session to populate initial client state
        session_cart = request.session.get('cart', {})
        
        return render(request, 'ordering/menu.html', {
            'categories': categories,
            'session_cart_json': json.dumps(session_cart),
        })


class CartSyncView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            cart = data.get('cart', {})
            # Sanity clean the cart payload
            clean_cart = {}
            for item_id, qty in cart.items():
                if str(item_id).isdigit() and int(qty) > 0:
                    clean_cart[str(item_id)] = int(qty)
            
            request.session['cart'] = clean_cart
            request.session.modified = True
            return JsonResponse({'status': 'success', 'cart': clean_cart})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


class CheckoutView(View):
    def post(self, request):
        # Retrieve session-stored cart state
        cart = request.session.get('cart', {})
        if not cart:
            return JsonResponse({'status': 'error', 'message': 'Your shopping cart is empty.'}, status=400)
        
        # Parse customer checkout details
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
            customer_name = data.get('customer_name', '').strip()
            customer_phone = data.get('customer_phone', '').strip()
            table_number = data.get('table_number', '').strip()
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid request parameters.'}, status=400)
            
        if not customer_name or not customer_phone or not table_number:
            return JsonResponse({'status': 'error', 'message': 'Name, phone, and table number are required.'}, status=400)
            
        # Execute transactional block (all-or-nothing checkout)
        try:
            with transaction.atomic():
                # Lock MenuItem rows being referenced to protect item cost audit details
                menu_item_ids = [int(k) for k in cart.keys()]
                menu_items = MenuItem.objects.select_for_update().filter(id__in=menu_item_ids, is_available=True)
                
                # Check for pricing discrepancies/out-of-stock items
                menu_items_map = {item.id: item for item in menu_items}
                if len(menu_items_map) != len(menu_item_ids):
                    missing = set(menu_item_ids) - set(menu_items_map.keys())
                    return JsonResponse({
                        'status': 'error', 
                        'message': f'Some items are currently unavailable. (IDs: {list(missing)})'
                    }, status=400)
                
                # Create parent order
                order = Order(
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    table_number=table_number,
                    status='RECEIVED'
                )
                if request.user.is_authenticated:
                    order.user = request.user
                order.save()
                
                # Calculate subtotal, apply taxes (8% modifier), and link items
                order_items = []
                subtotal = Decimal('0.00')
                for item_id_str, qty in cart.items():
                    item_id = int(item_id_str)
                    menu_item = menu_items_map[item_id]
                    quantity = int(qty)
                    subtotal += menu_item.price * quantity
                    
                    order_items.append(OrderItem(
                        order=order,
                        menu_item=menu_item,
                        quantity=quantity,
                        unit_price=menu_item.price
                    ))
                
                tax = subtotal * Decimal('0.08')
                total = subtotal + tax
                
                # Save total pricing metadata back to the order
                order.total_price = total
                order.save(update_fields=['total_price'])
                
                # Bulk create items
                OrderItem.objects.bulk_create(order_items)
                
            # Erase session cart records on transaction commitment
            if 'cart' in request.session:
                del request.session['cart']
            request.session.modified = True
            
            return JsonResponse({
                'status': 'success',
                'order_uuid': str(order.unique_id),
                'message': 'Order placed successfully!'
            })
            
        except Exception as err:
            return JsonResponse({'status': 'error', 'message': f'Transaction failed: {str(err)}'}, status=500)


class OrderTrackingView(View):
    def get(self, request, order_uuid):
        order = get_object_or_404(Order.objects.prefetch_related('items__menu_item'), unique_id=order_uuid)
        return render(request, 'ordering/track.html', {'order': order})


class OrderStatusAPI(View):
    def get(self, request, order_uuid):
        order = get_object_or_404(Order, unique_id=order_uuid)
        return JsonResponse({
            'status': order.status,
            'status_display': order.get_status_display(),
            'updated_at': order.updated_at.isoformat()
        })


class KitchenDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'ordering/kitchen.html'
    login_url = 'login'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Load active orders sorted chronologically to optimize prep order
        active_orders = Order.objects.filter(
            status__in=['RECEIVED', 'PREPARING', 'READY']
        ).order_by('created_at').prefetch_related('items__menu_item')
        context['orders'] = active_orders
        context['active_count'] = active_orders.count()
        return context


class KitchenTransitionView(LoginRequiredMixin, View):
    login_url = 'login'
    
    def post(self, request, order_id):
        try:
            data = json.loads(request.body)
            target_status = data.get('status', '').upper()
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid payload.'}, status=400)
            
        # Strict validation mapping for valid status transition jumps
        VALID_TRANSITIONS = {
            'RECEIVED': ['PREPARING', 'CANCELLED'],
            'PREPARING': ['READY', 'CANCELLED'],
            'READY': ['COMPLETED'],
            'COMPLETED': [],
            'CANCELLED': []
        }
        
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(id=order_id)
                current_status = order.status
                
                if target_status not in VALID_TRANSITIONS.get(current_status, []):
                    return JsonResponse({
                        'status': 'error', 
                        'message': f'Illegal state transition from {current_status} to {target_status}'
                    }, status=400)
                
                order.status = target_status
                order.save(update_fields=['status'])
                
            return JsonResponse({
                'status': 'success',
                'order_id': order.id,
                'new_status': order.status,
                'new_status_display': order.get_status_display()
            })
        except Order.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Order not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# Auth System Views
class UserLoginView(LoginView):
    template_name = 'ordering/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        if self.request.user.is_staff:
            return reverse_lazy('kitchen_dashboard')
        return reverse_lazy('menu')


class UserSignupView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('menu')
        form = UserCreationForm()
        return render(request, 'ordering/signup.html', {'form': form})
        
    def post(self, request):
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registered and logged in successfully!")
            return redirect('menu')
        return render(request, 'ordering/signup.html', {'form': form})


class UserLogoutView(View):
    def get(self, request):
        logout(request)
        return redirect('menu')

