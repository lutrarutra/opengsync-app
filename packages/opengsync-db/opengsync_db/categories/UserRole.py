from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class UserRoleEnum(DBEnum):
    label: str
    icon: str
    insider: bool = False


class UserRole(ExtendedEnum):
    label: str
    icon: str
    insider: bool
    DEACTIVATED = UserRoleEnum(0, "Deactivated", "🔒", False)
    ADMIN = UserRoleEnum(1, "Admin", "🤓", True)
    BIOINFORMATICIAN = UserRoleEnum(2, "Bioinformatician", "👨🏾‍💻", True)
    TECHNICIAN = UserRoleEnum(3, "Technician", "🧑🏽‍🔬", True)
    CLIENT = UserRoleEnum(4, "Client", "👶🏻", False)

    @classmethod
    def insiders(cls) -> list["UserRole"]:
        return [
            cls.ADMIN,
            cls.BIOINFORMATICIAN,
            cls.TECHNICIAN
        ]
    
    @property
    def select_name(self) -> str:
        return self.icon
    
    @property
    def display_name(self) -> str:
        return f"{self.label} {self.icon}"
