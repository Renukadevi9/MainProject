import uuid
from django.db import models
from django.core.validators import MinValueValidator, RegexValidator
from django.contrib.auth.models import User

class Category(models.Model):
    name = models.CharField(max_length=50, unique=True, db_index=True)
    icon_class = models.CharField(max_length=50, help_text="FontAwesome class name, e.g., 'fa-hamburger'")
    slug = models.SlugField(max_length=50, unique=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0.01)])
    is_veg = models.BooleanField(default=True)
    is_spicy = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True, db_index=True)
    image_url = models.URLField(max_length=500, blank=True, help_text="Direct link to premium food image")

    def __str__(self):
        return self.name



class Order(models.Model):
    STATUS_CHOICES = [
        ('RECEIVED', 'Received'),
        ('PREPARING', 'Preparing'),
        ('READY', 'Ready to Serve'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    unique_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    customer_name = models.CharField(max_length=100)
    
    phone_validator = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    customer_phone = models.CharField(max_length=15, validators=[phone_validator])
    table_number = models.CharField(max_length=10)
    status = models.CharField(max_length=15, default='RECEIVED', choices=STATUS_CHOICES, db_index=True)

    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.id} (Table {self.table_number}) - {self.status}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name} for Order {self.order.id}"

