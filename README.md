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

## 🪟 Windows installer

CI builds `VrikshaStudiosDesk-Setup-<version>.exe` for every pull request (Actions run → *Artifacts*), and attaches it to a GitHub Release when a tag like `v1.0.0` is pushed. A `.sha256` file sits next to it.

- Installs for the current user only (no administrator password) and asks once for the server address.
- Shop data (local database, invoices, server address) is kept in `%LOCALAPPDATA%\VrikshaStudios`, and survives upgrades and uninstalling. To change the server later, edit `API_BASE_URL` in the `.env` file there.
- **Updates:** the installed program checks GitHub Releases a few seconds after it starts and every 6 hours. When a newer version is published it shows a banner (and a Windows notification if the window is behind other programs). **Update now** downloads the installer, checks its SHA-256, runs it silently and the app reopens by itself; nothing installs without that click. The sidebar's *Updates* button checks on demand. Development copies and branch builds never prompt.
- The installer is **not code-signed**, so Windows SmartScreen shows "Unknown publisher" the first time: choose *More info → Run anyway*. A signing certificate is the only fix and is a paid extra.
- Build it locally: `pip install -r requirements.txt -r requirements-build.txt`, then `./packaging/build.ps1`, then `ISCC /DAppVersion=1.0.0 packaging\installer.iss` (needs Inno Setup 6).

---

## 📜 License

The source code is under the **MIT License** (see `LICENSE`). The Windows installer also bundles PyQt6 (GPL v3) and Qt (LGPL v3), so the installer as a whole is provided under the GPL v3; the full texts are installed with it (`THIRD_PARTY_LICENSES.txt`).
