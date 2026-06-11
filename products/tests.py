from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from accounts.models import User
from products.models import Product, Category

class ProductExportTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_superuser(
            username='admin', 
            password='password123',
            email='admin@example.com'
        )
        self.client.force_authenticate(user=self.user)
        
        self.category = Category.objects.create(name="Crackers")
        self.product1 = Product.objects.create(
            name="Sparkler",
            brand="Standard",
            category=self.category,
            purchase_price=10.0,
            selling_price=15.0,
            stock_quantity=100
        )
        self.product2 = Product.objects.create(
            name="Flower Pot",
            brand="Standard",
            category=self.category,
            purchase_price=20.0,
            selling_price=30.0,
            stock_quantity=50
        )

    def test_export_csv(self):
        url = reverse('product-export-csv')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertTrue(response['Content-Disposition'].startswith('attachment; filename="inventory_export.csv"'))
        
        content = response.content.decode('utf-8')
        lines = content.splitlines()
        
        # Header + 2 products
        self.assertEqual(len(lines), 3)
        self.assertIn('Name,Brand,Category,SKU,Purchase Price,Selling Price,MRP,No Of Case,Cent In Per Case,Total Stock (Cent),Min Stock Level', lines[0])
        self.assertIn('Sparkler', content)
        self.assertIn('Flower Pot', content)

    def test_export_csv_filtered(self):
        url = reverse('product-export-csv')
        response = self.client.get(url, {'search': 'Sparkler'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.content.decode('utf-8')
        lines = content.splitlines()
        
        self.assertEqual(len(lines), 2) # Header + 1 product
        self.assertIn('Sparkler', content)
        self.assertNotIn('Flower Pot', content)
