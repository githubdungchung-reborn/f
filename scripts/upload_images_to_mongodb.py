import os
import sys
from pymongo import MongoClient, UpdateOne
from datetime import datetime, UTC
import re
from typing import Optional, List, Dict
from urllib.parse import urlparse

class MongoDBUploader:
    def __init__(self, connection_string: str, database_name: str = 'fgo_database'):
        self.client = MongoClient(connection_string, 
                                serverSelectionTimeoutMS=5000,
                                connectTimeoutMS=5000)
        self.db = self.client[database_name]
        self.collection = self.db.images
        
    def create_indexes(self):
        """Create necessary indexes for better query performance"""
        self.collection.create_index([("code", 1)], unique=True)
        self.collection.create_index([("number", 1)])
        self.collection.create_index([("prefix", 1)])
        
    def parse_image_url(self, url: str) -> Dict:
        """Parse image URL to extract metadata"""
        parsed = urlparse(url)
        path_parts = parsed.path.split('/')
        
        # Extract image code from filename
        filename = path_parts[-1]
        code = filename.replace('.jpg', '')
        prefix = code[0]
        number = int(code[1:])
        
        # Extract folder information
        folder = '/'.join(path_parts[:-1])
        
        return {
            'code': code,
            'prefix': prefix,
            'number': number,
            'folder': folder,
            'url': url
        }
        
    def process_log_file(self, log_file: str) -> bool:
        """Process log file containing image URLs"""
        try:
            operations = []
            current_time = datetime.now(UTC)
            
            with open(log_file, 'r') as f:
                for line in f:
                    # Skip empty lines
                    if not line.strip():
                        continue
                        
                    # Use the entire line as URL after stripping whitespace
                    url = line.strip()
                    
                    # Skip if URL is empty
                    if not url:
                        continue
                        
                    metadata = self.parse_image_url(url)
                    
                    # Prepare update operation
                    doc = {
                        **metadata,
                        'updated_at': current_time
                    }
                    
                    operations.append(
                        UpdateOne(
                            {'code': metadata['code']},
                            {
                                '$set': doc,
                                '$setOnInsert': {'created_at': current_time}
                            },
                            upsert=True
                        )
                    )
                    
                    # Process in batches of 1000
                    if len(operations) >= 1000:
                        self._execute_bulk_operations(operations)
                        operations = []
            
            # Process remaining operations
            if operations:
                self._execute_bulk_operations(operations)
                
            return True
            
        except Exception as e:
            print(f"Error processing log file: {e}")
            return False
            
    def _execute_bulk_operations(self, operations: List[UpdateOne]):
        """Execute bulk write operations with error handling"""
        try:
            result = self.collection.bulk_write(operations)
            print(f"Processed batch: {result.upserted_count} inserted, {result.modified_count} modified")
        except Exception as e:
            print(f"Error executing bulk write: {e}")
            raise

def main():
    # Get environment variables
    mongodb_url = os.environ.get('MONGODB_URL')
    if not mongodb_url:
        print("Error: MONGODB_URL environment variable not set")
        return False
        
    # Get log file path from command line argument
    if len(sys.argv) != 2:
        print("Usage: python upload_images_to_mongodb.py <log_file_path>")
        return False
        
    log_file = sys.argv[1]
    if not os.path.exists(log_file):
        print(f"Error: Log file not found: {log_file}")
        return False
        
    try:
        # Initialize uploader
        uploader = MongoDBUploader(mongodb_url)
        
        # Create indexes
        uploader.create_indexes()
        
        # Process log file
        success = uploader.process_log_file(log_file)
        
        return success
        
    except Exception as e:
        print(f"Error in main execution: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 