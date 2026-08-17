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

    def test_health_analytics_valuation_unit_aware(self):
        """Verify health_analytics correctly calculates valuation for cent mode and piece mode products."""
        # Cent Product: 10 cases * 10 cent/cs = 100 cents = 1000 pieces in DB
        # purchase_price = 100 (per cent), selling_price = 150 (per cent)
        # Expected total_value = 100 cents * 100 = 10,000 (NOT 1,00,000!)
        Product.objects.create(
            name="Cent Item",
            brand="Standard",
            category=self.category,
            purchase_price=Decimal("100.00"),
            selling_price=Decimal("150.00"),
            no_of_case=10,
            cent_in_per_cs=Decimal("10.0"),
            entry_mode="cent"
        )

        # Piece Product: 5 cases * 10 pieces/cs = 50 pieces in DB
        # purchase_price = 10 (per piece), selling_price = 15 (per piece)
        # Expected total_value = 50 pieces * 10 = 500
        Product.objects.create(
            name="Piece Item",
            brand="Standard",
            category=self.category,
            purchase_price=Decimal("10.00"),
            selling_price=Decimal("15.00"),
            no_of_case=5,
            cent_in_per_cs=Decimal("1.0"), # 1.0 cent = 10 pieces/cs
            entry_mode="piece"
        )

        self.client.force_authenticate(user=self.owner)
        url = "/api/products/health_analytics/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        
        data = response.data["data"]
        # Total value = 10,000 (Cent Item) + 500 (Piece Item) = 10,500
        self.assertAlmostEqual(data["total_inventory_value"], 10500.0)
        # Potential revenue = 15,000 (Cent Item) + 750 (Piece Item) = 15,750
        self.assertAlmostEqual(data["potential_revenue"], 15750.0)

