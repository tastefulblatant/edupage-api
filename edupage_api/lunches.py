import json
from datetime import datetime
from typing import List, Optional

from edupage_api.exceptions import (FailedToChangeLunchError,
                                    FailedToRateException,
                                    NotLoggedInException)
from edupage_api.module import EdupageModule, Module, ModuleHelper


class Rating:
    def __init__(self, mysql_date, boarder_id,
                 quality_average, quantity_average,
                 quality_ratings, quantity_ratings):
        self.quality_ratings = quality_ratings
        self.quality_average = quality_average

        self.quantity_ratings = quantity_ratings
        self.quantity_average = quantity_average

        self.__date = mysql_date
        self.__boarder_id = boarder_id

    def rate(self, edupage: EdupageModule, quantity: int, quality: int):
        if not edupage.is_logged_in:
            raise NotLoggedInException()

        request_url = f"https://{edupage.subdomain}.edupage.org/menu/"

        data = {
            "akcia": "ulozHodnotenia",
            "stravnikid": self.__boarder_id,
            "mysqlDate": self.__date,
            "jedlo_dna": "2",
            "kvalita": str(quality),
            "mnozstvo": str(quantity)
        }

        response = edupage.session.post(request_url, data=data)
        parsed_response = json.loads(response.content.decode())

        error = parsed_response.get("error")
        if error is None or error != "":
            raise FailedToRateException()


class Menu:
    def __init__(self, name: str, allergens: str, weight: str, number: str, rating: Optional[Rating]):
        self.name = name
        self.allergens = allergens
        self.weight = weight
        self.number = number
        self.rating = rating


class Lunch:
    def __init__(self, served_from: Optional[datetime], served_to: Optional[datetime],
                 amount_of_foods: int, chooseable_menus: list[str],
                 can_be_changed_until: datetime, title: str,
                 menus: List[Menu], date: datetime,
                 boarder_id: str):
        self.date = date
        self.served_from = served_from
        self.served_to = served_to
        self.amount_of_foods = amount_of_foods
        self.chooseable_menus = chooseable_menus
        self.can_be_changed_until = can_be_changed_until
        self.title = title
        self.menus = menus
        self.__boarder_id = boarder_id

    def __iter__(self):
        return iter(self.menus)

    def __make_choice(self, edupage: EdupageModule, choice_str: str):
        request_url = f"https://{edupage.subdomain}.edupage.org/menu/"

        boarder_menu = {
            "stravnikid": self.__boarder_id,
            "mysqlDate": self.date.strftime("%Y-%m-%d"),
            "jids": {
                "2": choice_str
            },
            "view": "pc_listok",
            "pravo": "Student"
        }

        data = {
            "akcia": "ulozJedlaStravnika",
            "jedlaStravnika": json.dumps(boarder_menu)
        }

        response = edupage.session.post(request_url, data=data).content.decode()

        if json.loads(response).get("error") != "":
            raise FailedToChangeLunchError()

    def choose(self, edupage: EdupageModule, number: int):
        letters = "ABCDEFGH"
        letter = letters[number - 1]

        self.__make_choice(edupage, letter)

    def sign_off(self, edupage: EdupageModule):
        self.__make_choice(edupage, "AX")


class Lunches(Module):
    @ModuleHelper.logged_in
    def get_lunch(self, date: datetime):
        date_strftime = date.strftime("%Y%m%d")
        request_url = f"https://{self.edupage.subdomain}.edupage.org/menu/?date={date_strftime}"
        response = self.edupage.session.get(request_url).content.decode()

        boarder_id = response.split("var stravnikid = \"")[1].split("\"")[0]
        lunch_data = json.loads(response.split("var novyListok = ")[1].split(";")[0])

        lunch = lunch_data.get(date.strftime("%Y-%m-%d"))

        if lunch is None:
            return None

        lunch = lunch.get("2")

        served_from_str = lunch.get("vydaj_od")
        served_to_str = lunch.get("vydaj_do")

        if served_from_str:
            served_from = datetime.strptime(served_from_str, "%H:%M")
        else:
            served_from = None

        if served_to_str:
            served_to = datetime.strptime(served_to_str, "%H:%M")
        else:
            served_to = None

        title = lunch.get("nazov")

        amount_of_foods = lunch.get("druhov_jedal")
        chooseable_menus = list(lunch.get("choosableMenus").keys())

        can_be_changed_until = lunch.get("zmen_do")

        menus = []

        for food in lunch.get("rows"):
            if not food:
                continue

            name = food.get("nazov")
            allergens = food.get("alergenyStr")
            weight = food.get("hmotnostiStr")
            number = food.get("menuStr")
            rating = None

            if number is not None:
                number = number.replace(": ", "")
                rating = lunch.get("hodnotenia")
                if rating is not None and rating:
                    rating = rating.get(number)

                    [quality, quantity] = rating

                    quality_average = quality.get("priemer")
                    quality_ratings = quality.get("pocet")

                    quantity_average = quantity.get("priemer")
                    quantity_ratings = quantity.get("pocet")

                    rating = Rating(date.strftime("%Y-%m-%d"), boarder_id,
                                    quality_average, quantity_average,
                                    quality_ratings, quantity_ratings)
                else:
                    rating = None
            menus.append(Menu(name, allergens, weight, number, rating))

        return Lunch(served_from, served_to, amount_of_foods,
                     chooseable_menus, can_be_changed_until,
                     title, menus, date, boarder_id)
