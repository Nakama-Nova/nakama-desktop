from enum import Enum


class UserRole(str, Enum):
    OWNER = "owner"
    MANAGER = "manager"
    SALES = "sales"
    ACHARI = "achari"
    WORKER = "worker"
    ARTISAN = "artisan"
    ACCOUNTANT = "accountant"  # the CA: reads the books and reports, changes nothing
