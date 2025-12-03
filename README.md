# TogetherNow

## Description
This project is a web application with a Python Flask backend and a static HTML frontend.

## Setup Instructions

### Prerequisites
- Python 3.x installed
- pip installed

### Installation

1.  **Install Dependencies:**
    Navigate to the project root and run:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configuration:**
    Ensure you have the `serviceAccountKey.json` placed in the `backend/` directory. This file is required for Firebase authentication and is not included in the repository for security reasons.

### Running the Application

1.  **Start the Backend Server:**
    ```bash
    python backend/app.py
    ```
    The server will start on `http://localhost:5000` (or the configured port).

2.  **Access the Frontend:**
    Open `index.html` in your web browser.

## Project Structure
- `index.html`: Frontend entry point.
- `backend/`: Contains the Flask application and related files.
    - `app.py`: Main application logic.
    - `seed_data.py`: Script to seed initial data.
