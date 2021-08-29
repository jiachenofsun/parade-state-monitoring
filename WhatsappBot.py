# Import required packages
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
)

from datetime import datetime
from itertools import permutations
from textdistance import lcsstr
import pandas as pd
from utility_functions import Vehicle

import gspread
import time
import logging
import traceback
import shutil

logging.basicConfig(
    level=logging.INFO,
    filename="log.txt",
    filemode="w",
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%d/%m/%y %H:%M:%S",
)

# Initializing Bot
TO_UPDATE = "'Mandai TOs'"


def match_name(df_to_match, name):
    # Using longest common substring similarity (lcsstr).
    # This is due to name variations being often rearrangements of each other.
    # The matching occurs in two steps.
    # First, the rank _must_ match.
    # Second, from those with matching ranks, match len(lcsstr) > 3
    rank = name.split()[0].upper()
    name = "".join([x.lower() for x in name.split()[1:]])

    # First, ensure the rank matches
    matched_rank = df_to_match.RANK == rank

    def max_common_permutated_token(name_to_check, name):
        possible_names = ["".join(p) for p in permutations(name_to_check.split())]
        lcsseq_length = [len(lcsstr(name.lower(), x.lower())) for x in possible_names]
        return max(lcsseq_length)

    score = [max_common_permutated_token(x, name) for x in df_to_match.NAME]

    # Ensure that names with non-matching ranks do not get selected
    # Reminder: [True, False] * [1, 2] = [1, 0]
    matched_score = score * matched_rank
    max_score = max(matched_score)

    if max_score > 3:
        match = [x == max_score for x in matched_score]
        if sum(match) > 1:
            logging.info(f"{name}: Multiple Names Matched!")
            return [False] * len(score)
        else:
            return match
    else:  # No matching rank AND name
        return [False] * len(score)


def parse_reply(message, name, vcom_name):
    # This is a reply to a message.
    # This is quite annoying as nsometimes we get replies to replies.
    # That we mean that we see only the sender, and not the full details.
    logging.info(f"Parsing Reply: {name} commanded by {vcom_name}")

    # Selecting the person who indicated an update
    match = match_name(PS_df[["RANK", "NAME"]], name)
    if vcom_name:
        match_vcom = match_name(PS_df[["RANK", "NAME"]], vcom_name)
        match = [any(t) for t in zip(match, match_vcom)]

    row = PS_df[match].index
    veh = None

    # Let's join up the message for searching...
    joined_msg = "".join([x.lower() for x in message])

    # This is a good reply, praise the lord
    # In addition, name and vcom_name should both be populated
    # Unless one of them isn't our people, but then I don't
    # care about it anyway.
    if "to" in joined_msg and "vc" in joined_msg:
        # Let's get the plate number
        plate = ""
        for m in message[1:]:
            if ":" in m:
                a, b = m.split(":")
            elif len(m.split()) > 1:
                a, b = m.split()
            else:
                a = ""
                b = ""

            if "mid" in a.lower():
                plate = b.strip()
                break

        # Normally the case, unless detail left before bot started
        if plate in ongoingDetails.keys():
            veh = ongoingDetails[plate]

    # This is a shitty reply :<
    # Name and only name is always populated for shitty replies
    elif len(ongoingDetails) > 0:
        row_n = row.array[0]
        formal_name = PS_df.at[row_n, "RANK/NAME"]
        for k, v in ongoingDetails.items():
            # Found the detail
            if formal_name in [v.to, v.vcom]:
                veh = v
                row = PS_df[
                    (PS_df["RANK/NAME"] == v.to) | (PS_df["RANK/NAME"] == v.vcom)
                ].index
                break
    else:
        # I don't understand how ongoingDetails can be empty and still parsing a reply
        pass

    # Updating latest message
    PS_df.loc[row, "LatestUpdate"] = f"{datetime.today()}\n" + "\n".join(message)

    # These would ensure that all 'RTU' then 'reach' messages are found
    # ...regardless of destination
    # Assessments always come back to MHC
    for i in ["rtu", "assessment", "to mh"]:
        if i in joined_msg and "reach" in joined_msg.split(i)[-1]:
            PS_df.loc[row, "STATUS"] = "PRESENT"
            try:
                if veh:
                    ongoingDetails.pop(veh.plate)
                    logging.info(f"RTU: {', '.join(str(veh).splitlines())}")
                    update_ongoingDetails()
                break
            except:
                logging.error(traceback.format_exc())
                logging.error(message)
                print(traceback.format_exc())

    update_PS()


def parse_movement(message, name, vcom_name):
    # We are sure that this is a movement from point A to B
    # This would normally necessitate the creation of a new Vehicle class.
    logging.info(f"Parsing Movement: {name} commanded by {vcom_name}")

    # Selecting the person who indicated an update
    match = match_name(PS_df[["RANK", "NAME"]], name)
    if any(match):
        name_row = PS_df[match].index.array[0]
        name = PS_df.at[name_row, "RANK/NAME"]

    if vcom_name:
        match_vcom = match_name(PS_df[["RANK", "NAME"]], vcom_name)
        match = [any(t) for t in zip(match, match_vcom)]

        if any(match_vcom):
            vcom_row = PS_df[match_vcom].index.array[0]
            vcom_name = PS_df.at[vcom_row, "RANK/NAME"]

    row = PS_df[match].index

    # Updating Parade State
    PS_df.loc[row, "LatestUpdate"] = f"{datetime.today()}\n" + "\n".join(message)
    PS_df.loc[row, "STATUS"] = "DETAIL"
    try:
        # There is no need to check for existing detail because it is a new movement anyway
        message_details = {
            "model": message[0].lower().split("mov")[0].split("x")[-1].strip(),
            "to": name,
            "vcom": vcom_name,
            "plate": None,
            "purpose": None,
        }

        for m in message[1:]:
            if ":" in m:
                a, b = m.split(":")
            elif len(m.split()) > 1:
                fragments = m.split()
                a = fragments[0]
                b = " ".join(fragments[1:])
            else:
                a = ""
                b = ""

            if "mid" in a.lower():
                message_details["plate"] = b.strip()
            elif "purpose" in a.lower():
                message_details["purpose"] = b.strip()

        if message_details["plate"]:
            veh = Vehicle(**message_details)
            ongoingDetails[message_details["plate"]] = veh
            logging.info(f"New movement logged: [{'], ['.join(str(veh).splitlines())}]")
            update_ongoingDetails()
    except:
        logging.error(traceback.format_exc())
        logging.error(message)
        print(traceback.format_exc())

    update_PS()


def parse_message(message, sender_str=None):
    name = None
    vcom_name = None
    for m in message:
        if m.lower().startswith("to"):
            name = m.split(":")[-1].strip()
        elif m.lower().startswith("vc"):
            vcom_name = m.split(":")[-1].strip()

    # Suppose this is a reply to a reply, so no 'TO:'
    # This is assuming I saved their contacts
    # e.g. ['NAME', 'NAME', 'RTU', 'Reached', TIMESTAMP]
    # Unexpected behaviour if we are assessing fam for external people
    # in which case vcom and to is the same person.
    if not name:
        name_rank = sender_str.split(",")[0].replace("(", "")
        name_split = name_rank.split()
        name = " ".join(name_split[-1:] + name_split[:-1])

    start_line = 0
    if message[0][0].isnumeric():
        start_line = 0
    elif message[0] == message[1] or (
        message[2][0].isnumeric() and ":" not in message[2]
    ):
        start_line = 2
    else:
        start_line = 1

    if message[0] == message[1] or "reach" in message[-2].lower():
        parse_reply(message[start_line:], name, vcom_name)
    else:
        parse_movement(message[start_line:], name, vcom_name)


def initialize_PS(keep_remarks=False):
    PS_content = PSsheet.get_all_values()[1:]
    if keep_remarks:
        PS_df = pd.DataFrame(PS_content).drop(
            columns=list(range(8, len(PS_content[0])))
        )
    else:
        PS_df = pd.DataFrame(PS_content).drop(
            columns=list(range(7, len(PS_content[0])))
        )
    PS_df.columns = [x.strip() for x in PS_df.iloc[0]]
    PS_df = (
        PS_df.set_index("S/N")
        .drop(index="S/N")
        .replace("", pd.NA)
        .dropna(thresh=2)
        .convert_dtypes()
        .replace(pd.NA, "")
    )
    PS_df.index = pd.to_numeric(PS_df.index)
    PS_df["LatestUpdate"] = ""

    # In case ASA cleared the STATUS, assuming they WFH
    PS_df["STATUS"] = PS_df.STATUS.fillna("WFH")
    PS_df["VOCATION"] = PS_df.VOCATION.fillna("TBD")
    PS_df["PLATOON"] = PS_df.PLATOON.fillna("TBD")
    PS_df["RANK/NAME"] = PS_df.RANK + " " + PS_df.NAME
    logging.debug("INITIALIZATION: " + PS_df.to_string())
    return PS_df


def update_PS():
    logging.debug("WRITING: " + PS_df.to_string())
    sh.values_clear("'Auto_Generated'!A1:H100")
    GENsheet.batch_update(
        [
            {"range": "I2", "values": [[str(datetime.today())]]},
            {
                "range": "A1",
                "values": [list(PS_df.reset_index().columns)]
                + PS_df.to_records().tolist(),
            },
        ]
    )
    logging.info(f"Parade State updated at: {datetime.today()}")


def update_ongoingDetails():
    sh.values_clear("'Daily Reporting'!B2:B100")
    DRsheet.update(
        "B2",
        [[str(datetime.today())], [], []]
        + [[f"{k}\n{str(v)}"] for k, v in ongoingDetails.items()],
    )


def check_messages(last_checked):
    # Do not change last checked time if every element fails
    cur_time = last_checked
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located(
            (By.XPATH, f"//*[contains(@title, {TO_UPDATE})]")
        )
    )
    driver.find_element_by_xpath(f"//*[contains(@title, {TO_UPDATE})]").click()

    try:
        results = driver.find_elements_by_class_name("message-in")
        results[0].send_keys(Keys.PAGE_UP)
    except StaleElementReferenceException:
        logging.warning("Stale Element Reference Exception during scrolling up.")

    try:
        results = driver.find_elements_by_class_name("message-in")
        results[-1].send_keys(Keys.END)
    except StaleElementReferenceException:
        logging.warning("Stale Element Reference Exception during scrolling down.")

    results = driver.find_elements_by_class_name("message-in")
    for elem in results:

        # The time of the message is hidden here
        time_str_elements = elem.find_elements_by_class_name("copyable-text")

        # Deleted message have no such element
        if len(time_str_elements) > 0:
            # Parsing the time string
            time_str = time_str_elements[0].get_attribute("data-pre-plain-text")
            sender_str = time_str.split("]")[-1].strip()
            time_str = time_str[time_str.find("[") + 1 : time_str.find("]")]

            hour_str, date_str = time_str.split(",")
            hour, minute = [int(x) for x in hour_str.split(":")]
            day, month, year = [int(x) for x in date_str.split("/")]
            message_time = datetime(year, month, day, hour % 24, minute)

            # sanity check wtf why they switch the day and dates
            if (message_time - datetime.today()).days > 1:
                month, day, year = [int(x) for x in date_str.split("/")]
                message_time = datetime(year, month, day, hour % 24, minute)

            try:
                message = elem.text
                # Filters out irrelevant messages and detail forecast message
                if (
                    ("MID" in message)
                    and any([x in message.lower() for x in ["to:", "to :"]])
                ) or all([x in message.lower() for x in ["rtu", "reach"]]):
                    message = message.splitlines()
                    # Remove empty lines
                    message = [x for x in message if x]
                    if message_time >= last_checked:
                        logging.info(f"Message sent at: {time_str}")
                        parse_message(message, sender_str)

                        # Update the checked time
                        today = datetime.today()
                        cur_time = datetime(
                            today.year, today.month, today.day, today.hour, today.minute
                        )

            except StaleElementReferenceException:
                logging.warning("Element expired while reading element text...")

    return cur_time


def generate_temperature_list(is_morning=True):
    df = initialize_PS(keep_remarks=True)
    df["STATUS"] = df.STATUS.fillna("WFH")

    today = datetime.today()
    if is_morning:
        time_str = "0800hrs"
    else:
        time_str = "1500hrs"

    return_str = (
        "*Temperature Monitoring*\n\n"
        + "Grouping : CMTL (Mandai Hill Node)\n"
        + f"Date: {today.strftime('%d%m%y')}\n"
        + f"Time: {time_str}\n\n"
        + f"{'='*22}\n\n"
        + f"Total Strength: {len(df)}\n"
        + f"Present Strength: {sum(df.STATUS.str.contains('PRESENT').dropna()|df.STATUS.str.contains('REST').dropna())+1}\n"
        + "({0[HQ PLATOON]} from HQ, {0[PLATOON 1]} from PLT 1, {0[PLATOON 2]} from PLT 2, 1 AMB TO)\n".format(
            {p: sum(x.STATUS.str.contains("PRESENT")) for p, x in df.groupby("PLATOON")}
        )
        + f"Temperature Taking Strength: {sum(df.STATUS.str.contains('PRESENT').dropna())}\n"
        + "({0[HQ PLATOON]} from HQ, {0[PLATOON 1]} from PLT 1, {0[PLATOON 2]} from PLT 2)\n\n\n".format(
            {p: sum(x.STATUS.str.contains("PRESENT")) for p, x in df.groupby("PLATOON")}
        )
        + "Reason for not taking (Rank/Name & Reason):"
    )

    for label, gp in df.groupby("STATUS"):
        return_str += "\n\n"
        if any([x in label for x in ["PRESENT", "RS"]]):
            return_str = return_str[:-2]
        elif "AO" in label:
            amb_gp = gp[gp.REMARKS.str.contains("AMB DUTY")]
            return_str += "AMBULANCE DUTY (1 pax)\n" + "\n".join(
                [
                    "{0}. {1}".format(i + 1, amb_gp.iloc[i]["RANK/NAME"])
                    for i in range(len(amb_gp))
                ]
            )
            ao_gp = gp[~(gp.REMARKS.str.contains("AMB DUTY"))]
            if len(ao_gp) > 0:
                return_str += f"\n\nAO ({len(ao_gp)} pax)\n" + "\n".join(
                    [
                        "{0}. {1}".format(i + 1, ao_gp.iloc[i]["RANK/NAME"])
                        for i in range(len(ao_gp))
                    ]
                )
        else:
            return_str += f"{label} ({len(gp)} pax)\n" + "\n".join(
                [
                    "{0}. {1}".format(i + 1, gp.iloc[i]["RANK/NAME"])
                    for i in range(len(gp))
                ]
            )

    rs_gp = df[df.STATUS.str.contains("RS")]
    return_str += (
        f"\n\n{'='*22}\n\n"
        + f"Any report sick ({len(rs_gp)} pax): (Rank/Name & Reason)\n"
        + "\n".join(
            [
                "{0}. {1}".format(i + 1, rs_gp.iloc[i]["RANK/NAME"])
                for i in range(len(rs_gp))
            ]
        )
    )
    DRsheet.batch_update(
        [
            {"range": "A2", "values": [[str(datetime.today())]]},
            {"range": "A5", "values": [[return_str]]},
        ]
    )
    logging.info(f"Temperature List Updated at: {datetime.today()}")


###############################################################################
### Starting Application                                                    ###
###############################################################################

# Loading Parade State
logging.info("Started")
gc = gspread.service_account()
sh = gc.open_by_key("1qxDItGZJWAXTyvR6HK8p2g4gF49rrtwQ6sTfZe7z9I4")

PSsheet = sh.worksheet("MHN Parade State")  # Parade State
GENsheet = sh.worksheet("Auto_Generated")  # Machine Generated Sheet
DRsheet = sh.worksheet("Daily Reporting")  # Daily reporting sheet

# On first initialization
today = datetime.today()
last_checked = datetime(today.year, today.month, today.day, 8, 0)
PS_df = initialize_PS()
generate_temperature_list(is_morning=datetime.today().hour < 12)

## Starting WhatsApp Bot Chrome Driver
options = Options()
options.headless = True
options.add_argument("user-data-dir=D:\\Downloads\\whatsapp_profiles\\")
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36"
)
options.add_argument("disable-gpu")
options.add_argument("window-size=960,1080")
driver = webdriver.Chrome(
    executable_path=".\chromedriver_win32\chromedriver.exe", options=options
)

driver.get("https://web.whatsapp.com/")
time.sleep(15)
driver.save_screenshot(".\screenshot.png")

# Wait for QR code to be scanned, timeout 120 for Whatsapp Web
WebDriverWait(driver, 120).until(
    EC.invisibility_of_element_located((By.CLASS_NAME, "landing-wrapper"))
)
time.sleep(10)

ongoingDetails = dict()
# Run continuously
while True:
    try:
        last_checked = check_messages(last_checked)
    except:
        logging.error(traceback.format_exc())
        print(traceback.format_exc())

    driver.save_screenshot(".\screenshot.png")
    time_now = datetime.today()
    logging.debug(f"Last Run at: {time_now}")
    print(f"Last Run at: {time_now}", flush=True)

    try:
        if DRsheet.get("A4") == [["TRUE"]]:
            PS_df = initialize_PS()
            update_PS()
            generate_temperature_list(is_morning=datetime.today().hour < 12)
            DRsheet.update_cell(4, 1, "FALSE")
    except:
        logging.error(traceback.format_exc())
        print(traceback.format_exc())

    # Reinitialize on a weekday
    if time_now.weekday() < 5:  # Monday == 0
        if time_now.hour == 8 and time_now.minute == 10:
            PS_df = initialize_PS()
            update_PS()
            generate_temperature_list(is_morning=True)

        elif time_now.hour == 14 and time_now.minute == 10:
            generate_temperature_list(is_morning=False)

    time.sleep(60 - time.time() % 60)
