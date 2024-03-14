from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass
class UserRoleEnum(DBEnum):
    icon: str

    def is_insider(self) -> bool:
        return self in (UserRole.ADMIN, UserRole.BIOINFORMATICIAN, UserRole.TECHNICIAN)


class UserRole(ExtendedEnum[UserRoleEnum], enum_type=UserRoleEnum):
    ADMIN = UserRoleEnum(1, "Admin", "🤓")
    BIOINFORMATICIAN = UserRoleEnum(2, "Bioinformatician", "👨🏾‍💻")
    TECHNICIAN = UserRoleEnum(3, "Technician", "🧑🏽‍🔬")
    CLIENT = UserRoleEnum(4, "Client", "👶🏾")
