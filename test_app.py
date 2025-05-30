import requests
import threading
import time
import random
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Dict, List, Tuple
import json
import string

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_random_string(length: int) -> str:
    """Generate a random string of specified length"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_random_user() -> Tuple[str, str, str]:
    """Generate random user data"""
    # Generate username (8-12 characters)
    username_length = random.randint(8, 12)
    username = generate_random_string(username_length)
    
    # Generate email
    email_domain = random.choice(['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com'])
    email = f"{username}@{email_domain}"
    
    # Generate password (12-16 characters)
    password_length = random.randint(12, 16)
    password = generate_random_string(password_length)
    
    return username, email, password

class TestUser:
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.username, self.email, self.password = generate_random_user()
        self.base_url = base_url
        self.session = requests.Session()
        self.score = 0
        self.annotations = 0
        self.is_registered = False

    def register(self) -> bool:
        """Register a new user"""
        try:
            response = self.session.post(
                f"{self.base_url}/register",
                data={
                    "username": self.username,
                    "email": self.email,
                    "password": self.password
                }
            )
            self.is_registered = response.status_code == 200
            return self.is_registered
        except Exception as e:
            logger.error(f"Registration failed for {self.username}: {str(e)}")
            return False

    def login(self) -> bool:
        """Login with user credentials"""
        try:
            if not self.is_registered:
                if not self.register():
                    return False
            
            response = self.session.post(
                f"{self.base_url}/login",
                data={
                    "username": self.username,
                    "password": self.password
                }
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Login failed for {self.username}: {str(e)}")
            return False

    def get_comparison(self) -> Dict:
        """Get a comparison with random delay"""
        try:
            # Add random delay to simulate human behavior
            time.sleep(random.uniform(0.5, 2.0))
            response = self.session.get(f"{self.base_url}/compare")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Failed to get comparison for {self.username}: {str(e)}")
            return None

    def submit_answer(self, image_id: str, answer: str) -> bool:
        """Submit answer with random delay"""
        try:
            # Add random delay to simulate human behavior
            time.sleep(random.uniform(0.3, 1.5))
            response = self.session.post(
                f"{self.base_url}/submit",
                data={"image_id": image_id, "answer": answer}
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to submit answer for {self.username}: {str(e)}")
            return False

    def gamble(self) -> bool:
        """Attempt to gamble with random delay"""
        try:
            # Add random delay to simulate human behavior
            time.sleep(random.uniform(0.2, 1.0))
            response = self.session.post(
                f"{self.base_url}/gamble",
                json={"prize": {"points": random.randint(1, 20)}}
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to gamble for {self.username}: {str(e)}")
            return False

def simple_test():
    """Test basic functionality with a single user"""
    logger.info("Starting simple test...")
    user = TestUser()
    
    # Test registration and login
    assert user.register(), "Registration failed"
    logger.info(f"Registration successful for {user.username}")
    
    assert user.login(), "Login failed"
    logger.info(f"Login successful for {user.username}")
    
    # Test getting comparison
    comparison = user.get_comparison()
    assert comparison is not None, "Failed to get comparison"
    logger.info("Got comparison successfully")
    
    # Test submitting answer
    answer = random.choice(["Yes", "No"])
    assert user.submit_answer(comparison["image_id"], answer), "Failed to submit answer"
    logger.info(f"Submitted answer '{answer}' successfully")
    
    # Test gambling
    assert user.gamble(), "Failed to gamble"
    logger.info("Gambling successful")
    
    logger.info("Simple test completed successfully")

def concurrent_user_test(num_users: int = 5, num_actions: int = 10):
    """Test concurrent users performing actions"""
    logger.info(f"Starting concurrent test with {num_users} users...")
    
    def user_workflow():
        user = TestUser()
        if not user.register():
            logger.error(f"User {user.username} failed to register")
            return
        
        if not user.login():
            logger.error(f"User {user.username} failed to login")
            return
        
        logger.info(f"User {user.username} started workflow")
        
        for _ in range(num_actions):
            # Get comparison
            comparison = user.get_comparison()
            if comparison is None:
                continue
            
            # Simulate human behavior with random delays
            time.sleep(random.uniform(0.5, 2.0))
            
            # Submit random answer with bias towards "Yes" (60% chance)
            answer = "Yes" if random.random() < 0.6 else "No"
            user.submit_answer(comparison["image_id"], answer)
            
            # Occasionally gamble (30% chance)
            if random.random() < 0.3:
                time.sleep(random.uniform(0.2, 1.0))
                user.gamble()
    
    # Create and start threads for each user
    threads = []
    for _ in range(num_users):
        thread = threading.Thread(target=user_workflow)
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    logger.info("Concurrent test completed")

def stress_test(num_users: int = 20, duration_seconds: int = 30):
    """Stress test with many users over a duration"""
    logger.info(f"Starting stress test with {num_users} users for {duration_seconds} seconds...")
    
    def user_workflow(stop_event: threading.Event):
        user = TestUser()
        if not user.register() or not user.login():
            return
        
        logger.info(f"Stress user {user.username} started")
        
        while not stop_event.is_set():
            try:
                # Simulate more realistic user behavior
                comparison = user.get_comparison()
                if comparison:
                    # Random delay to simulate human behavior
                    time.sleep(random.uniform(0.3, 1.5))
                    
                    # Submit answer with bias towards "Yes"
                    answer = "Yes" if random.random() < 0.6 else "No"
                    user.submit_answer(comparison["image_id"], answer)
                    
                    # Occasionally take a longer break (10% chance)
                    if random.random() < 0.1:
                        time.sleep(random.uniform(2.0, 5.0))
                    
                    # Occasionally gamble (25% chance)
                    if random.random() < 0.25:
                        time.sleep(random.uniform(0.2, 1.0))
                        user.gamble()
                
                # Random delay between actions
                time.sleep(random.uniform(0.1, 0.5))
                
            except Exception as e:
                logger.error(f"Error in user {user.username}: {str(e)}")
    
    stop_event = threading.Event()
    threads = []
    
    # Start user threads
    for _ in range(num_users):
        thread = threading.Thread(target=user_workflow, args=(stop_event,))
        threads.append(thread)
        thread.start()
    
    # Run for specified duration
    time.sleep(duration_seconds)
    stop_event.set()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    logger.info("Stress test completed")

if __name__ == "__main__":
    try:
        # Run simple test
        simple_test()
        
        # Run concurrent test
        concurrent_user_test(num_users=5, num_actions=10)
        
        # Run stress test
        stress_test(num_users=20, duration_seconds=30)
        
    except Exception as e:
        logger.error(f"Test suite failed: {str(e)}")
        raise 