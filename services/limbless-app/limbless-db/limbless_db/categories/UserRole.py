from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class UserRoleEnum(DBEnum):
    icon: str
    insider: bool = False

    def is_insider(self) -> bool:
        return self.insider


class UserRole(ExtendedEnum[UserRoleEnum], enum_type=UserRoleEnum):
    ADMIN = UserRoleEnum(1, "Admin", "🤓", True)
    BIOINFORMATICIAN = UserRoleEnum(2, "Bioinformatician", "👨🏾‍💻", True)
    TECHNICIAN = UserRoleEnum(3, "Technician", "🧑🏽‍🔬", True)
    CLIENT = UserRoleEnum(4, "Client", "👶🏾")
