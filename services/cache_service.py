import time
import threading

class SimpleCache:
    def __init__(self):
        self.cache = {}
        self.lock = threading.Lock()
    
    def get(self, key):
        """Get data from cache if it exists and is not expired"""
        with self.lock:
            if key in self.cache and self.cache[key]['expiry'] > time.time():
                return self.cache[key]['data']
        return None
    
    def set(self, key, data, expiry_seconds=300):
        """Store data in cache with expiration"""
        with self.lock:
            self.cache[key] = {
                'data': data,
                'expiry': time.time() + expiry_seconds
            }
    
    def clear(self, pattern=None):
        """Clear cache entries matching pattern"""
        with self.lock:
            if not pattern:
                self.cache = {}
                return
            
            keys_to_delete = []
            for key in self.cache:
                if pattern in key:
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del self.cache[key]

# Create a global cache instance
cache = SimpleCache()

# Export simple functions for easier imports
def get_cached_data(key):
    return cache.get(key)

def set_cached_data(key, data, expiry_seconds=300):
    cache.set(key, data, expiry_seconds)

def clear_cache(pattern=None):
    cache.clear(pattern) 