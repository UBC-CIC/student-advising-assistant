from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import os

# Setup WebDriver (Chrome in this example, but you can use any browser)
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service)

# URL of the Flask application
BASE_URL = "https://student-advising-demo.us-west-2.elasticbeanstalk.com"

# Flag to not login again
ALREADY_LOGGED_IN = False

# List of questions to submit
questions = [
    "Can I add a minor in fourth year?",
    "When do I have to apply to add a commerce minor?",
    "I have an average of 54% and I have failed two courses this term. I haven't failed a course before this. Can I continue?",
    "My average was 40%, what happens now?",
    "I missed my exam because I had covid, what do I do?",
    "I slept through my exam, what do I do?",
    "Does ENGL 110 count for the arts requirement?",
    "Can I take PSYC 120 for the arts requirement?",
    "Does physics 100 count for the arts requirement?",
    "CPSC 110 waitlist is full, what do I do?",
    "I am in second year major chemistry, do I have to take MATH 221?",
    "I am in second year major chemistry, do I need to take any biology courses?",
    "Can I take CHEM 233 instead of CHEM 203?"
]

def submit_question_and_feedback(question):
    global ALREADY_LOGGED_IN
    
    # Navigate to the home page
    driver.get(BASE_URL)

    # Login to the application if needed
    if not ALREADY_LOGGED_IN:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(os.environ["USERNAME"])
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "password"))).send_keys(os.environ["PASSWORD"], Keys.RETURN)
        ALREADY_LOGGED_IN = True

    # Wait for the page to load
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "question")))

    # Fill out the question form
    question_textarea = driver.find_element(By.ID, "question")
    question_textarea.send_keys(question)

    # Submit the form
    submit_button = driver.find_element(By.ID, "submit")
    driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "submit")))
    driver.execute_script("arguments[0].click();", submit_button)

    # Wait for the answer page to load
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "feedback-form")))

    # Provide feedback
    feedback_yes_button = driver.find_element(By.ID, "feedback-yes")
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "feedback-yes")))
    driver.execute_script("arguments[0].click();", feedback_yes_button)

    # Wait for feedback form to be visible
    WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "feedback-comments")))

    # Fill out the feedback form
    feedback_comments = driver.find_element(By.ID, "feedback-comments")
    feedback_comments.send_keys("This feedback is submitted from a test script. Please ignore.")

    # Select most relevant reference (if available)
    feedback_reference_select = driver.find_element(By.NAME, "feedback-reference-select")
    feedback_reference_select.send_keys(Keys.DOWN)  # Selecting the first option (None or first reference)

    # Submit the feedback form
    feedback_submit_button = driver.find_element(By.ID, "feedback-submit")
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "feedback-submit")))
    driver.execute_script("arguments[0].click();", feedback_submit_button)

    # Optionally, wait to ensure feedback is submitted before continuing
    time.sleep(2)

def main():
    for question in questions:
        submit_question_and_feedback(question)
    driver.quit()

if __name__ == "__main__":
    main()