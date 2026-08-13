from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from accounts.models import User
from products.models import Product, Category


class ProductInventoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = Category.objects.create(name="Crackers", description="Firecrackers category")
        
        # Create Owner user for API actions
        self.owner = User.objects.create_user(
            email="owner@fataka.com",
            username="owner",
            password="securepassword123",
            role=User.OWNER
        )

    def test_product_creation_with_decimal_cent(self):
        """Verify that creating a product with a decimal cent_in_per_cs correctly calculates stock_quantity."""
        product = Product.objects.create(
            name="Sparklers 10",
            brand="Standard",
            category=self.category,
            purchase_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            no_of_case=10,
            cent_in_per_cs=Decimal("2.3")  # 2.3 cents = 23 pieces
        )
        # stock_quantity should be 10 (cases) * 2.3 (cent_in_per_cs) * 10 (multiplier) = 230 pieces
        self.assertEqual(product.stock_quantity, 230)
        self.assertEqual(product.total_stock_in_cent, Decimal("23.0"))

    def test_product_update_recalculates_stock(self):
        """Verify that updating stock-related fields recalculates stock_quantity correctly with decimals."""
        product = Product.objects.create(
            name="Sparklers 10",
            brand="Standard",
            category=self.category,
            purchase_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            no_of_case=10,
            cent_in_per_cs=Decimal("2.0")
        )
        self.assertEqual(product.stock_quantity, 200)

        # Update cent_in_per_cs to a decimal
        product.cent_in_per_cs = Decimal("2.5")
        product.save()
        self.assertEqual(product.stock_quantity, 250)

    def test_api_create_product_with_decimal(self):
        """Verify adding product through the API view with a decimal cent_in_per_cs."""
        self.client.force_authenticate(user=self.owner)
        url = reverse("product-list")
        data = {
            "name": "Chakkars Special",
            "brand": "Standard",
            "category": self.category.id,
            "purchase_price": "120.00",
            "selling_price": "180.00",
            "no_of_case": 5,
            "cent_in_per_cs": "2.3",  # Decimal cent value
            "min_stock_level": 5
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        
        # Verify saved in DB correctly
        product = Product.objects.get(name="Chakkars Special")
        self.assertEqual(product.cent_in_per_cs, Decimal("2.30"))
        # 5 cases * 2.3 cent * 10 = 115 pieces
        self.assertEqual(product.stock_quantity, 115)
