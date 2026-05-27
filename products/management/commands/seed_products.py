import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from products.models import Product, Category, generate_unique_sku

class Command(BaseCommand):
    help = 'Seeds the database with a highly curated list of 71 realistic firecracker products'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete all existing products before seeding'
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write(self.style.WARNING('Clearing existing products and categories from the database...'))
            deleted_count, _ = Product.objects.all().delete()
            deleted_cats, _ = Category.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Successfully cleared {deleted_count} products and {deleted_cats} categories!'))

        # Hand-curated list of 71 realistic firecracker products
        # Standard Wholesale/Retail pricing scheme:
        # mrp: Catalog retail price
        # selling_price: 60% of MRP (40% discount)
        # purchase_price: 50% of selling price (50% wholesale margin)
        curated_products = [
            # 1. SPARKLERS (FULBAJHI) - 10 Products
            {"name": "7cm Green Sparklers (10 Pcs/Box)", "brand": "Standard", "mrp": 50.00},
            {"name": "7cm Red Sparklers (10 Pcs/Box)", "brand": "Standard", "mrp": 50.00},
            {"name": "10cm Electric Sparklers (10 Pcs/Box)", "brand": "Standard", "mrp": 80.00},
            {"name": "12cm Gold Sparklers (10 Pcs/Box)", "brand": "Kaliswari", "mrp": 120.00},
            {"name": "15cm Electric Sparklers (10 Pcs/Box)", "brand": "Kaliswari", "mrp": 150.00},
            {"name": "30cm Jumbo Sparklers (5 Pcs/Box)", "brand": "Sri Krishna", "mrp": 200.00},
            {"name": "Magic Wand Crackling Sparklers (5 Pcs/Box)", "brand": "Sony", "mrp": 250.00},
            {"name": "50cm Mega Sparklers (5 Pcs/Box)", "brand": "Anil", "mrp": 350.00},
            {"name": "Green Sparklers Deluxe (10 Pcs/Box)", "brand": "Standard", "mrp": 90.00},
            {"name": "Crackling Sparklers Deluxe (10 Pcs/Box)", "brand": "Supreme", "mrp": 130.00},

            # 2. FLOWER POTS (ANAR) - 10 Products
            {"name": "Flower Pots Small (10 Pcs/Box)", "brand": "Standard", "mrp": 150.00},
            {"name": "Flower Pots Medium (10 Pcs/Box)", "brand": "Standard", "mrp": 250.00},
            {"name": "Flower Pots Large (10 Pcs/Box)", "brand": "Kaliswari", "mrp": 400.00},
            {"name": "Flower Pots Special (5 Pcs/Box)", "brand": "Kaliswari", "mrp": 300.00},
            {"name": "Flower Pots Giant (5 Pcs/Box)", "brand": "Sri Krishna", "mrp": 500.00},
            {"name": "Aakash Tara Anar (2 Pcs/Box)", "brand": "Sony", "mrp": 600.00},
            {"name": "Color Changing Flower Pots (5 Pcs/Box)", "brand": "Supreme", "mrp": 450.00},
            {"name": "Super Deluxe Anar (5 Pcs/Box)", "brand": "Anil", "mrp": 550.00},
            {"name": "Golden Rain Flower Pots (5 Pcs/Box)", "brand": "Arasan", "mrp": 350.00},
            {"name": "Green Fountain Flower Pots (5 Pcs/Box)", "brand": "Arasan", "mrp": 350.00},

            # 3. GROUND SPINNERS (CHAKKAR) - 8 Products
            {"name": "Ground Wheel Small (10 Pcs/Box)", "brand": "Standard", "mrp": 100.00},
            {"name": "Ground Wheel Big (10 Pcs/Box)", "brand": "Standard", "mrp": 180.00},
            {"name": "Chakkar Special (10 Pcs/Box)", "brand": "Kaliswari", "mrp": 200.00},
            {"name": "Zameen Chakkar Power (5 Pcs/Box)", "brand": "Sri Krishna", "mrp": 250.00},
            {"name": "Deluxe Spinners with Sound (5 Pcs/Box)", "brand": "Sony", "mrp": 300.00},
            {"name": "Jumbo Ground Wheel (5 Pcs/Box)", "brand": "Anil", "mrp": 350.00},
            {"name": "Disco Chakkar Multi-color (10 Pcs/Box)", "brand": "Supreme", "mrp": 220.00},
            {"name": "Double Sound Chakkar (5 Pcs/Box)", "brand": "Arasan", "mrp": 280.00},

            # 4. ROCKETS - 8 Products
            {"name": "Baby Rocket (10 Pcs/Box)", "brand": "Standard", "mrp": 120.00},
            {"name": "Whistling Rocket (10 Pcs/Box)", "brand": "Standard", "mrp": 220.00},
            {"name": "Lunik Rocket (5 Pcs/Box)", "brand": "Kaliswari", "mrp": 300.00},
            {"name": "Space Rocket Deluxe (5 Pcs/Box)", "brand": "Sri Krishna", "mrp": 450.00},
            {"name": "Two Sound Rocket (5 Pcs/Box)", "brand": "Sony", "mrp": 350.00},
            {"name": "Parachute Rocket (3 Pcs/Box)", "brand": "Anil", "mrp": 600.00},
            {"name": "Siren Rocket (5 Pcs/Box)", "brand": "Arasan", "mrp": 400.00},
            {"name": "Mega Space Voyager Rocket (2 Pcs/Box)", "brand": "Supreme", "mrp": 700.00},

            # 5. GARLANDS (MAAL/LAR) - 9 Products
            {"name": "28 Deluxe Maal (Single Pack)", "brand": "Standard", "mrp": 100.00},
            {"name": "56 Deluxe Maal (Single Pack)", "brand": "Standard", "mrp": 180.00},
            {"name": "100 Garlands (Laxmi Lar)", "brand": "Kaliswari", "mrp": 250.00},
            {"name": "1000 Garlands (Red Lar)", "brand": "Kaliswari", "mrp": 800.00},
            {"name": "2000 Garlands (Mega Lar)", "brand": "Sri Krishna", "mrp": 1500.00},
            {"name": "5000 Garlands (Monster Lar)", "brand": "Sri Krishna", "mrp": 3500.00},
            {"name": "10000 Garlands (Giga Lar)", "brand": "Sony", "mrp": 6500.00},
            {"name": "28 Chorsa Red Crackers", "brand": "Anil", "mrp": 90.00},
            {"name": "56 Chorsa Red Crackers", "brand": "Anil", "mrp": 160.00},

            # 6. ATOM BOMBS / SOUND CRACKERS - 7 Products
            {"name": "Classic Hydro Bomb (5 Pcs/Pack)", "brand": "Standard", "mrp": 150.00},
            {"name": "Bullet Crackers (10 Pcs/Pack)", "brand": "Standard", "mrp": 80.00},
            {"name": "King Bomb Giant (5 Pcs/Pack)", "brand": "Kaliswari", "mrp": 250.00},
            {"name": "Sultan Bomb (5 Pcs/Pack)", "brand": "Sri Krishna", "mrp": 300.00},
            {"name": "Laxmi Bomb Classic (10 Pcs/Pack)", "brand": "Sony", "mrp": 180.00},
            {"name": "Green Atom Bomb Heavy (5 Pcs/Pack)", "brand": "Supreme", "mrp": 200.00},
            {"name": "Deluxe Hydro Bomb Double Sound (5 Pcs)", "brand": "Anil", "mrp": 280.00},

            # 7. FANCY MULTI-SHOT AERIALS (SKY SHOTS) - 9 Products
            {"name": "7 Shot Fancy (Single)", "brand": "Standard", "mrp": 250.00},
            {"name": "12 Shot Multi-colour (Single)", "brand": "Standard", "mrp": 450.00},
            {"name": "30 Shot Sky Shot (Single)", "brand": "Kaliswari", "mrp": 950.00},
            {"name": "50 Shot Deluxe Aerial (Single)", "brand": "Sri Krishna", "mrp": 1600.00},
            {"name": "60 Shot Special Multi-colour (Single)", "brand": "Sony", "mrp": 2200.00},
            {"name": "120 Shot Magic Show (Single)", "brand": "Anil", "mrp": 4200.00},
            {"name": "240 Shot Mega Orchestral (Single)", "brand": "Supreme", "mrp": 8500.00},
            {"name": "Double Sound Aerial Shell (3 Pcs)", "brand": "Arasan", "mrp": 650.00},
            {"name": "Crackling Comet Sky Shot (Single)", "brand": "Standard", "mrp": 800.00},

            # 8. NOVELTY CRACKERS / KIDS FAVORITES - 10 Products
            {"name": "Magic Pops / Pop-pop (50 Packs)", "brand": "Standard", "mrp": 150.00},
            {"name": "Serpent Eggs / Black Snake (10 Packs)", "brand": "Standard", "mrp": 100.00},
            {"name": "Peacock Fountain Novelty (2 Pcs)", "brand": "Kaliswari", "mrp": 280.00},
            {"name": "Butterfly Flying Novelty (5 Pcs)", "brand": "Sri Krishna", "mrp": 320.00},
            {"name": "Siren Whistling Wheels (5 Pcs)", "brand": "Sony", "mrp": 240.00},
            {"name": "Bijli Crackers Strip of 50", "brand": "Anil", "mrp": 80.00},
            {"name": "Bijli Crackers Strip of 100", "brand": "Anil", "mrp": 150.00},
            {"name": "Red Bijli Loose Pack of 100", "brand": "Arasan", "mrp": 130.00},
            {"name": "Cartoon Helicopter Spinner (5 Pcs)", "brand": "Supreme", "mrp": 350.00},
            {"name": "Twinkling Star Sparklers (10 Pcs)", "brand": "Standard", "mrp": 120.00}
        ]

        # Create Category objects in the database
        category_map = {}
        category_names = [
            'Sparklers',
            'Flower Pots',
            'Chakkars',
            'Rockets',
            'Garlands',
            'Atom Bombs',
            'Fancy Shots',
            'Novelties'
        ]
        
        for cat_name in category_names:
            cat, _ = Category.objects.get_or_create(name=cat_name)
            category_map[cat_name] = cat

        products_to_create = []
        used_skus = set()
        
        self.stdout.write(self.style.SUCCESS(f'Preparing to seed {len(curated_products)} premium curated firecracker products...'))

        for index, p_data in enumerate(curated_products):
            mrp_val = Decimal(str(p_data["mrp"]))
            selling_price_val = mrp_val * Decimal('0.60') # 40% discount
            purchase_price_val = selling_price_val * Decimal('0.50') # 50% margin

            # Setup realistic stock levels
            stock_quantity_val = random.randint(50, 300)
            min_stock_level_val = random.randint(10, 30)

            # Determine category based on index in list (strict hand-curated ordering)
            if index < 10:
                selected_cat = category_map['Sparklers']
            elif index < 20:
                selected_cat = category_map['Flower Pots']
            elif index < 28:
                selected_cat = category_map['Chakkars']
            elif index < 36:
                selected_cat = category_map['Rockets']
            elif index < 45:
                selected_cat = category_map['Garlands']
            elif index < 52:
                selected_cat = category_map['Atom Bombs']
            elif index < 61:
                selected_cat = category_map['Fancy Shots']
            else:
                selected_cat = category_map['Novelties']

            product = Product(
                name=p_data["name"],
                brand=p_data["brand"],
                category=selected_cat,
                purchase_price=purchase_price_val.quantize(Decimal('0.00')),
                selling_price=selling_price_val.quantize(Decimal('0.00')),
                mrp=mrp_val.quantize(Decimal('0.00')),
                stock_quantity=stock_quantity_val,
                min_stock_level=min_stock_level_val,
                is_active=True
            )

            # Generate unique SKU
            while True:
                sku = generate_unique_sku()
                if sku not in used_skus:
                    product.sku = sku
                    used_skus.add(sku)
                    break
            
            products_to_create.append(product)

        # Bulk create the products in one transaction
        Product.objects.bulk_create(products_to_create)

        self.stdout.write(self.style.SUCCESS(f'Successfully seeded {len(products_to_create)} premium firecracker products!'))
