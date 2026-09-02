Personal ERP (Offline-First)

A local, privacy-first personal application designed to centralize daily life management by combining financial control, meal planning, and pantry management into a single modular interface.

🚀 Key Features
💰 Finance:
 - Management of current accounts, cash, and investment brokers (e.g., Directa, Binance) with multi-currency support (EUR and JPY) and live/offline exchange rates.  
 - Recording of expenses, income, and internal transfers (excluded from live expense statistics).  
 - Management of recurring expenses and income with quick execution.  
 - In-place editable transaction history and monthly category-aggregated reports.  
 📦 Possessions & Pantry:
 - Tracking of household inventory with intelligent measurement unit management and automatic conversions.  
 - Automatic clearing of depleted pantry items with direct transfer to the shopping list.  
 - Checkout feature that deducts funds from the chosen account, records the financial transaction, and refills the pantry.  
 🍳 Meals & Kitchen:
 - Recipe archive linked to ingredients.  
 - Weekly calendar for planning meal slots (Breakfast, Lunch, Dinner) with context management (At Home, Out, Offered by Me).  
 - Automatic consumption of ingredients from the pantry or immediate logging of restaurant costs.  
 - Integration with a local AI assistant (Ollama) for parsing natural language text and automatically populating the calendar.  
 ⚙️ Security & Backup:
 - Integrated system for automatic SQLite database backups with historical restore points.  


 📁 Repository Structure
 The project adopts a strictly decoupled and distributed architecture designed to separate business logic and data persistence from the user interface in view of future mobile migrations:  



 Plaintextpersonal_erp/
│
├── core/                     # Global configurations and constants
│
├── database/                 # Persistence management and SQLite queries
│   ├── __init__.py
│   ├── connection.py         # Active DB connection and pragmas
│   ├── scheme.py             # Initialization script and table creation
│   └── queries.py            # Support CRUD functions
│
├── services/                 # Business logic (Pure Python, no UI)
│   ├── __init__.py
│   ├── currency_service.py   # Exchange rates management and Frankfurter cache
│   ├── inventory_service.py  # Inventory, unit, and auto-shopping management
│   └── meal_service.py       # Recipes, calendar, and Ollama parsing management
│
├── ui/                       # User Interface (Streamlit)
│   ├── __init__.py
│   ├── tab_finance.py        # Finance area view
│   ├── tab_possessions.py    # Possessions & Shopping area view
│   ├── tab_meals.py          # Meals & Kitchen area view
│   └── tab_settings.py       # Settings & Backup view
│
├── backups/                  # Archive of .db database safety copies
│
├── app.py                    # Main entrypoint (launches the app and mounts UI views)
├── requirements.txt          # Project software dependencies
└── finance_food.db           # Local SQLite database (excluded from Git)