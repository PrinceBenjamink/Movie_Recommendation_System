from django.core.management.base import BaseCommand
from movies.mongodb_client import check_mongodb_connection, client, db

class Command(BaseCommand):
    help = 'Check MongoDB connection status and display database information'

    def handle(self, *args, **options):
        is_connected = check_mongodb_connection()
        
        if is_connected:
            self.stdout.write(self.style.SUCCESS('MongoDB connection: SUCCESSFUL'))
            
            # Get database stats
            try:
                db_stats = db.command('dbStats')
                collections = db.list_collection_names()
                
                self.stdout.write(f"Database: {db.name}")
                self.stdout.write(f"Collections: {', '.join(collections)}")
                self.stdout.write(f"Storage size: {db_stats.get('storageSize', 0) / 1024 / 1024:.2f} MB")
                self.stdout.write(f"Data size: {db_stats.get('dataSize', 0) / 1024 / 1024:.2f} MB")
                self.stdout.write(f"Objects: {db_stats.get('objects', 0)}")
                
                # Show document counts for main collections
                for collection in ['users', 'watchlists', 'search_history', 'viewing_history']:
                    if collection in collections:
                        count = db[collection].count_documents({})
                        self.stdout.write(f"Collection '{collection}': {count} documents")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Connected but couldn't get stats: {e}"))
        else:
            self.stdout.write(self.style.ERROR('MongoDB connection: FAILED'))
            self.stdout.write("Please check if MongoDB server is running and connection settings are correct.")