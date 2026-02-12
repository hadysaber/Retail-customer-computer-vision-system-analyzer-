# Retail Analytics System - Run Instructions

Your system is now fully configured and connected to Supabase (Cloud Database).

## 1. Verify Configuration
Ensure your `config.py` contains the correct connection string:
- **Status**: [CONNECTED] (Verified with `init_db.py`)
- **Database**: PostgreSQL (Supabase Pooler)

## 2. Start the AI Vision System (Data Collection)
This script opens your camera, detects people, tracks their movements, and sends data to the cloud.

1.  Open a **New Terminal** in VS Code.
2.  Run the following command:
    ```resh
    python editedOnlyOneID.py
    ```
3.  **To Stop**: Press `q` in the camera window or `Ctrl+C` in the terminal.

## 3. Start the Analytics Dashboard (Visualization)
This script reads the data from the cloud and displays real-time charts.

1.  Open a **Second Terminal** (Click `+` in the terminal panel).
2.  Run the following command:
    ```bash
    streamlit run dashboard.py
    ```
3.  This will automatically open your web browser to `http://localhost:8501`.

## 4. Troubleshooting
- **Database Connection Error?**
    - Run `python init_db.py` again to check the connection.
    - Check `config.py` for typos.
- **Missing Libraries?**
    - Run `pip install -r requirements.txt`.
