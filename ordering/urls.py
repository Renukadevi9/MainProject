from django.urls import path
from . import views

urlpatterns = [
    # Customer Menu and Checkout
    path('', views.MenuView.as_view(), name='menu'),
    path('cart/sync/', views.CartSyncView.as_view(), name='cart_sync'),
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    
    # Customer Live Order Tracking
    path('order/track/<uuid:order_uuid>/', views.OrderTrackingView.as_view(), name='order_tracking'),
    path('order/status/<uuid:order_uuid>/', views.OrderStatusAPI.as_view(), name='order_status_api'),
    
    # Kitchen Staff Dashboards
    path('kitchen/', views.KitchenDashboardView.as_view(), name='kitchen_dashboard'),
    path('kitchen/transition/<int:order_id>/', views.KitchenTransitionView.as_view(), name='kitchen_transition'),
    
    # Customer/Staff Authentication
    path('login/', views.UserLoginView.as_view(), name='login'),
    path('signup/', views.UserSignupView.as_view(), name='signup'),
    path('logout/', views.UserLogoutView.as_view(), name='logout'),
]
