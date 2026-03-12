# NakamaDesk Desktop 🪟

The feature-rich PyQt6 desktop client for the **FurniBiz ERP** system. Provides an intuitive interface for retail billing, inventory control, and business management.

---

## ✨ Features

- **Sales POS**: Rapid billing interface with item search and instant invoice printing.
- **Inventory Window**: Manage stock levels, view low-stock alerts, and update item details.
- **Sales History**: Complete log of transactions with date filtering and invoice reprinting capabilities.
- **Dashboard**: High-level overview of daily metrics (Sales, Revenue, Low Stock).
- **Customer CRM**: Manage customer profiles and search by phone number.
- **Event-Driven Refresh**: Real-time UI updates across windows using a centralized Event Bus.

## 🛠 Tech Stack

- **UI Framework**: [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
- **Networking**: [Requests](https://requests.readthedocs.io/)
- **Asynchronous Communication**: Custom Event Bus implementation.
- **Environment**: [Python Dotenv](https://github.com/theskumar/python-dotenv)

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Running instance of **NakamaDesk Backend**

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd nakama-desktop
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Setup Environment**:
   Create a `.env` file in the root directory:
   ```env
   API_BASE_URL=http://localhost:8000
   ```

5. **Start the Application**:
   ```bash
   python main.py
   ```

---

## 📁 Project Structure

```text
nakama-desktop/
├── assets/             # Images, icons, and styles
├── services/           # API Client, Session management, Event Bus
├── ui/                 # PyQt Screens and custom widgets
│   ├── dashboard_window.py
│   ├── inventory_window.py
│   ├── sales_screen.py
│   ├── sales_history_screen.py
│   ├── customers_screen.py
│   └── reports_screen.py
├── main.py             # Entry point
└── .gitignore
```

---

## 💡 Key Architecture

- **Service Layer**: Decouples UI logic from API communication.
- **Event Bus**: Handles cross-component signaling (e.g., updating the Dashboard when a Sale is created).
- **Session Management**: Securely stores JWT tokens for authenticated requests.

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.
