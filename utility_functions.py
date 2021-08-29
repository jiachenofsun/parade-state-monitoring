# Import required packages
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from datetime import datetime


class Vehicle:
    def __init__(self, model, plate, to, purpose, vcom=None):
        self.model = model
        self.plate = plate
        # self.avi = datetime.strptime(avi, "%d/%m/%Y").date()  # Parses dd/mm/yyyy
        # self.fe = datetime.strptime(fe, "%b %Y").date()  # Parses MMM yyyy
        self.to = to
        self.vcom = vcom
        self.purpose = purpose

    def __repr__(self):
        return {
            "model": self.model,
            "plate": self.plate,
            "to": self.to,
            "purpose": self.purpose,
            "vcom": self.vcom,
        }

    def __str__(self):
        return_str = (
            f"Model: {self.model}\n"
            + f"Plate: {self.plate}\n"
            + f"TO: {self.to}\n"
            + f"VCOM:{self.vcom}\n"
            + f"Purpose:{self.purpose}"
        )
        return return_str


class Detail:
    def __init__(
        self,
        vehicles,
        supporting_unit=None,
        reporting_location=None,
        destination=None,
        start_time=None,
        end_time=None,
    ):
        if not isinstance(vehicles, list):
            vehicles = [vehicles]
        self.vehicles = vehicles

        if not supporting_unit:
            self.supporting_unit = {
                "Name": None,
                "Purpose": None,
                "POC": None,
                "POC Contact": None,
            }

        self.reporting_location = reporting_location
        self.desination = desination
        self.start_time = start_time
        self.end_time = end_time
