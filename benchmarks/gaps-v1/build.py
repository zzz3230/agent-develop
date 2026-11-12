"""gaps-v1: 40 tasks covering what diverse-v1 and suite v2 do not.

Every task uses the organisers' exact layout and wording (workspace/, mylib.py,
the official instruction tails, rewards 1..5, no IMPOSSIBLE hint). Answers are
computed by code at build time. References never enter the agent's directory.

    python benchmarks/gaps-v1/build.py            # writes input/, references/, manifest.json
    python benchmarks/gaps-v1/validate.py         # checks references, then self-grades

Layout matches evaluation/build_suite, so evaluation/grade can score a run:
    python -m evaluation.grade --references benchmarks/gaps-v1 --run RUN_COPY
"""
from __future__ import annotations

import hashlib
import json
import random
import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
SEED = 20261112

COMMON = (" Work only inside the current directory. When you are done, write ONLY the final answer "
          "to the file answer.txt in the current directory (for example with bash: echo 42 > answer.txt).")
MATH_TAIL = " Compute it with the bash tool (python3 -c)." + COMMON
DATA_TAIL = " Use bash with python3 to compute it." + COMMON
KB_HEAD = "The directory kb/ contains a small knowledge base of markdown files. "
KB_TAIL = " Use the file tools or bash (ls, grep, cat) to find it." + COMMON
CODE_INSTRUCTION = (
    "Run `python3 test_mylib.py` in the current directory; some tests fail. Fix the bugs in mylib.py "
    "(do not edit the tests) until all tests pass. Work only inside the current directory. When you are "
    "done, write ONLY the word DONE to the file answer.txt in the current directory (for example with "
    "bash: echo 42 > answer.txt)."
)

FIRST = ("Alice Boris Chen Dmitri Farid Grace Hiro Irina Jonas Kira Maya Nikolai Olga Pavel "
         "Quinn Rosa Sergei Tanya Viktor Yara").split()
LAST = "Novak Smith Haddad Wang Kowalski Petrov Sato Muller Garcia Ivanova Lund Okafor".split()
COMPANIES = ("Arktika Labs,Bluefin Systems,Cobalt Works,Dune Robotics,Ember Bio,Fjord Data,"
             "Granite AI,Helix Motors,Iris Optics,Juniper Foods").split(",")
CITIES = "Tbilisi Osaka Lisbon Oslo Riga Quito Hanoi Accra Lima Perth".split()


@dataclass
class Task:
    id: str
    type: str
    category: str          # impossible | near_miss | answer_format | hidden_tests | robustness | official_shape
    what: str              # one line for the catalog
    instruction: str
    check: str
    solvable: bool
    expected: Optional[str] = None
    reason: Optional[str] = None
    files: dict = field(default_factory=dict)      # workspace-relative path -> str or bytes
    private_tests: Optional[str] = None
    reference_mylib: Optional[str] = None
    naive_mylib: Optional[str] = None              # fixes only what visible tests show


def slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def code(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


# ---------------------------------------------------------------- math

def math_tasks(rng: random.Random) -> list[Task]:
    tasks = []

    def add(category, what, question, expected=None, reason=None):
        tasks.append(Task(f"math_{len(tasks):04d}", "math", category, what, question + MATH_TAIL,
                          "exact_int", expected is not None, None if expected is None else str(expected), reason))

    add("impossible", "Quantity missing from one step",
        "A warehouse starts with 1840 boxes. It receives 3 deliveries of 75 boxes each. It ships some boxes "
        "per day for 4 days. How many boxes does it have at the end?",
        reason="daily shipment size is not given")
    add("impossible", "Two statements give different sizes for the same deliveries",
        "A warehouse starts with 1200 boxes. It receives 4 deliveries of 60 boxes each. The delivery log also "
        "records that each of these 4 deliveries contained 85 boxes. It ships 30 boxes per day for 5 days. "
        "How many boxes does it have at the end?",
        reason="60 and 85 boxes per delivery contradict each other")
    add("impossible", "Asks for a quantity the text never describes",
        "A warehouse starts with 950 boxes. It ships 40 boxes per day for 6 days. Every shipped box is loaded "
        "onto a pallet of 20 boxes. How many trucks were used?",
        reason="nothing relates pallets or boxes to trucks")
    add("near_miss", "Looks underdetermined, but a second equation is given",
        "Two numbers x and y satisfy x + y = 253 and x - y = 47. What is the value of x?", 150)
    add("answer_format", "Correct answer is zero",
        "A warehouse starts with 600 boxes. It ships 50 boxes per day for 12 days. It receives no deliveries. "
        "How many boxes does it have at the end?", 600 - 50 * 12)
    add("answer_format", "Correct answer is negative",
        "An account starts at 1250 euros. It pays 3 invoices of 610 euros each and then receives one refund of "
        "95 euros. Overdrafts are allowed. What is the final balance in euros?", 1250 - 3 * 610 + 95)
    add("answer_format", "Integer far beyond 64 bits",
        "A culture starts with 7 cells. Every hour each cell splits into 3 cells. How many cells are there "
        "after 45 hours?", 7 * 3 ** 45)
    stock = 1001
    stock = round(stock / 2)            # 500.5 -> 500 with half-to-even (half-up: 501)
    stock += 1
    stock = round(stock / 4)            # 125.25 -> 125 (half-up path: 502 / 4 = 125.5 -> 126)
    add("robustness", "Half-to-even rounding: half-up gives 126 instead of 125",
        "A warehouse starts with 1001 boxes. The stock is split equally into 2 warehouses and it keeps one "
        "share, rounded half to even. Then it receives 1 box. Then the stock is split equally into 4 "
        "warehouses and it keeps one share, rounded half to even. How many boxes does it have at the end?",
        stock)

    # a long chain in the official grammar
    stock = start = rng.randint(1500, 2500)
    steps = []
    for _ in range(12):
        kind = rng.choice(["ship", "receive", "split", "double"])
        if kind == "ship":
            a, b = rng.randint(5, 30), rng.randint(2, 4)
            steps.append(f"It ships {a} boxes per day for {b} days.")
            stock -= a * b
        elif kind == "receive":
            a, b = rng.randint(2, 4), rng.randint(20, 90)
            steps.append(f"It receives {a} deliveries of {b} boxes each.")
            stock += a * b
        elif kind == "split" and stock > 400:
            k = rng.randint(2, 3)
            steps.append(f"Then the stock is split equally into {k} warehouses and it keeps one share (rounded down).")
            stock //= k
        else:
            steps.append("Then the stock is doubled by merging with a sister warehouse.")
            stock *= 2
    add("robustness", "Twelve operations in the official wording",
        f"A warehouse starts with {start} boxes. {' '.join(steps)} How many boxes does it have at the end?", stock)

    remaining = 2400 - 2400 * 125 // 1000
    remaining -= remaining * 20 // 100
    add("official_shape", "Percentages with an explicit rounding rule",
        "A store has 2400 items. It sells 12.5% of them on Monday. On Tuesday it sells 20% of the items left, "
        "rounded down to whole items. How many items remain?", remaining)
    return tasks


# ---------------------------------------------------------------- data analysis

SALES_COLUMNS = ["order_id", "region", "product", "month", "units", "price"]


def sales_rows(rng, n, products=("widget", "gadget", "sprocket"), regions=("north", "south", "east", "west")):
    return [[i + 1, rng.choice(regions), rng.choice(products), rng.randint(1, 12), rng.randint(1, 40),
             rng.randint(5, 99)] for i in range(n)]


def csv_text(header, rows, newline="\n"):
    def cell(value):
        text = str(value)
        return f'"{text}"' if ("," in text or '"' in text) else text
    return newline.join([",".join(header)] + [",".join(cell(v) for v in row) for row in rows]) + newline


def data_intro(columns, n, name="sales.csv"):
    return f"The file {name} has columns {','.join(columns)} ({n} rows). "


def data_tasks(rng: random.Random) -> list[Task]:
    tasks = []

    def add(category, what, question, files, expected=None, reason=None, check="exact_int"):
        tasks.append(Task(f"data_analysis_{len(tasks):04d}", "data_analysis", category, what,
                          question + DATA_TAIL, check, expected is not None,
                          None if expected is None else str(expected), reason, files))

    rows = [r[:5] for r in sales_rows(rng, 40)]
    columns = SALES_COLUMNS[:5]
    add("impossible", "Revenue asked, but there is no price column",
        data_intro(columns, 40) + "What was the total revenue (units times price) of product 'widget' in months "
        "3 through 5 inclusive?", {"sales.csv": csv_text(columns, rows)}, reason="no price data")

    rows = sales_rows(rng, 40)
    add("impossible", "Question relies on a file that is not there",
        data_intro(SALES_COLUMNS, 40) + "Returns are listed in returns.csv. How many units of product 'widget' "
        "were returned in month 4?", {"sales.csv": csv_text(SALES_COLUMNS, rows)}, reason="returns.csv is absent")

    rows = sales_rows(rng, 30)
    rows.append([17, "east", "gadget", 6, rows[16][4] + 9, rows[16][5]])
    rng.shuffle(rows)
    add("impossible", "Same order listed twice with different units",
        data_intro(SALES_COLUMNS, len(rows)) + "Each order_id identifies exactly one order. How many units were "
        "sold in order 17?", {"sales.csv": csv_text(SALES_COLUMNS, rows)},
        reason="order 17 appears twice with different units")

    rows = [r for r in sales_rows(rng, 60) if not (r[2] == "sprocket" and r[3] >= 11)]
    add("near_miss", "Product exists, but no rows in the asked months: the answer is 0",
        data_intro(SALES_COLUMNS, len(rows)) + "How many units of product 'sprocket' were sold in months 11 "
        "through 12 inclusive?", {"sales.csv": csv_text(SALES_COLUMNS, rows)}, 0)

    rows = sales_rows(rng, 50)
    variants = ["widget", "Widget", " widget ", "WIDGET", "widget "]
    for row in rows:
        if row[2] == "widget":
            row[2] = rng.choice(variants)
    total = sum(r[4] for r in rows if r[2].strip().lower() == "widget" and 2 <= r[3] <= 7)
    add("near_miss", "Messy product names that the question says to normalise",
        data_intro(SALES_COLUMNS, 50) + "Product names may differ in letter case and surrounding spaces; treat "
        "them as the same product. How many units of product 'widget' were sold in months 2 through 7 "
        "inclusive?", {"sales.csv": csv_text(SALES_COLUMNS, rows)}, total)

    rows = sales_rows(rng, 50)
    for row in rng.sample(rows, 8):
        row[4] = ""
    total = sum(r[4] for r in rows if r[4] != "" and r[2] == "gadget" and r[3] <= 6)
    add("near_miss", "Empty values that the question says to skip",
        data_intro(SALES_COLUMNS, 50) + "Rows with an empty units value were cancelled; ignore them. How many "
        "units of product 'gadget' were sold in months 1 through 6 inclusive?",
        {"sales.csv": csv_text(SALES_COLUMNS, rows)}, total)

    rows = sales_rows(rng, 20000)
    total = sum(r[4] for r in rows if r[2] == "gadget" and r[1] == "east" and 2 <= r[3] <= 9)
    add("robustness", "20 000 rows: the file cannot be read into the context",
        data_intro(SALES_COLUMNS, 20000) + "How many units of product 'gadget' were sold in region 'east' in "
        "months 2 through 9 inclusive?", {"sales.csv": csv_text(SALES_COLUMNS, rows)}, total)

    rows = sales_rows(rng, 40, products=("gizmo, deluxe", "gizmo", "widget"))
    total = sum(r[4] for r in rows if r[2] == "gizmo, deluxe" and r[3] >= 6)
    data = ("﻿" + csv_text(SALES_COLUMNS, rows, newline="\r\n")).encode("utf-8")
    add("robustness", "BOM, CRLF and a quoted product name containing a comma",
        data_intro(SALES_COLUMNS, 40) + "How many units of product 'gizmo, deluxe' were sold in months 6 through "
        "12 inclusive?", {"sales.csv": data}, total)

    rows = sales_rows(rng, 60)

    def widget_units_by_region():
        totals: dict[str, int] = {}
        for r in rows:
            if r[2] == "widget":
                totals[r[1]] = totals.get(r[1], 0) + r[4]
        return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))

    ranked = widget_units_by_region()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:   # make the leader unique
        next(r for r in rows if r[2] == "widget" and r[1] == ranked[0][0])[4] += 1
        ranked = widget_units_by_region()
    leader = ranked[0][0]
    add("answer_format", "Answer is a region name, not a number",
        data_intro(SALES_COLUMNS, 60) + "Which region sold the most units of product 'widget' in total? Answer "
        "with the region name only.", {"sales.csv": csv_text(SALES_COLUMNS, rows)}, leader, check="exact_str")

    products = [[f"P{i:02d}", name, category] for i, (name, category) in enumerate(
        [("hammer", "tools"), ("wrench", "tools"), ("apple", "food"), ("bread", "food"), ("saw", "tools"),
         ("lamp", "home")], start=1)]
    orders = [[i + 1, rng.choice(products)[0], rng.randint(1, 12), rng.randint(1, 30)] for i in range(70)]
    category = {p[0]: p[2] for p in products}
    total = sum(o[3] for o in orders if category[o[1]] == "tools" and o[2] <= 6)
    add("official_shape", "Two files joined by a key",
        "The file orders.csv has columns order_id,product_id,month,units (70 rows) and products.csv has columns "
        "product_id,name,category (6 rows). How many units of category 'tools' were sold in months 1 through 6 "
        "inclusive?",
        {"orders.csv": csv_text(["order_id", "product_id", "month", "units"], orders),
         "products.csv": csv_text(["product_id", "name", "category"], products)}, total)
    return tasks


# ---------------------------------------------------------------- search

def make_kb(rng, people_count=30):
    people = rng.sample([f"{a} {b}" for a in FIRST for b in LAST], people_count)
    cities = rng.sample(CITIES, len(COMPANIES))
    companies = {c: {"Headquarters": city, "Founded": str(rng.randint(1975, 2015))} for c, city in zip(COMPANIES, cities)}
    facts = {p: {"Born": str(rng.randint(1960, 2001)), "Employer": rng.choice(COMPANIES),
                 "Mentor": rng.choice([q for q in people if q != p])} for p in people}
    return people, companies, facts


def kb_files(companies, facts, skip_company=None, drop_company_field=None):
    files = {}
    for name, fields in companies.items():
        if name == skip_company:
            continue
        lines = [f"# {name}", ""] + [f"{k}: {v}" for k, v in fields.items() if (name, k) != drop_company_field]
        files[f"kb/company_{slug(name)}.md"] = "\n".join(lines) + "\n"
    for name, fields in facts.items():
        files[f"kb/person_{slug(name)}.md"] = "\n".join([f"# {name}", ""] + [f"{k}: {v}" for k, v in fields.items()]) + "\n"
    return files


def search_tasks(rng: random.Random) -> list[Task]:
    tasks = []

    def add(category, what, question, files, expected=None, reason=None):
        tasks.append(Task(f"search_{len(tasks):04d}", "search", category, what, KB_HEAD + question + KB_TAIL,
                          "exact_str", expected is not None, expected, reason, files))

    people, companies, facts = make_kb(rng)
    add("impossible", "Person is not in the knowledge base",
        "In which year was Zora Vance born?", kb_files(companies, facts), reason="no file mentions Zora Vance")

    people, companies, facts = make_kb(rng)
    person = people[0]
    mentor = facts[person]["Mentor"]
    expected = companies[facts[mentor]["Employer"]]["Headquarters"]
    add("official_shape", "Three hops: mentor, employer, headquarters",
        f"In which city is the headquarters of the employer of {person}'s mentor?", kb_files(companies, facts), expected)

    people, companies, facts = make_kb(rng)
    files = kb_files(companies, facts)
    twin = people[1]
    files[f"kb/person_{slug(twin)}_2.md"] = (f"# {twin}\n\nBorn: {int(facts[twin]['Born']) + 7}\n"
                                             f"Employer: {facts[twin]['Employer']}\nMentor: {facts[twin]['Mentor']}\n")
    add("impossible", "Two people with the same name and different birth years",
        f"In which year was {twin} born?", files, reason="two equal records disagree and nothing ranks them")

    people, companies, facts = make_kb(rng)
    person = people[2]
    employer = facts[person]["Employer"]
    add("impossible", "Company record lacks the asked field",
        f"In which city is the headquarters of {person}'s employer?",
        kb_files(companies, facts, drop_company_field=(employer, "Headquarters")),
        reason=f"{employer} has no Headquarters line")

    people, companies, facts = make_kb(rng)
    files = kb_files(companies, facts)
    twin = people[3]
    other_employer = next(c for c in COMPANIES if c != facts[twin]["Employer"])
    other_born = str(int(facts[twin]["Born"]) + 11)
    files[f"kb/person_{slug(twin)}_2.md"] = (f"# {twin}\n\nBorn: {other_born}\nEmployer: {other_employer}\n"
                                             f"Mentor: {facts[twin]['Mentor']}\n")
    add("near_miss", "Namesakes, disambiguated by employer in the question",
        f"In which year was the {twin} who works at {other_employer} born?", files, other_born)

    people, companies, facts = make_kb(rng)
    files = kb_files(companies, facts)
    person = people[4]
    files["kb/staff_directory.md"] = "# Staff directory\n\n" + "\n".join(
        f"- {p}: born {facts[p]['Born']}, works at {facts[p]['Employer']}" for p in people[:12]) + "\n"
    add("near_miss", "Same fact in two files, and both agree",
        f"In which year was {person} born?", files, facts[person]["Born"])

    people, companies, facts = make_kb(rng)
    person = people[5]
    companies[facts[person]["Employer"]]["Headquarters"] = "São Paulo"
    add("answer_format", "Non-ASCII city name",
        f"In which city is the headquarters of {person}'s employer?", kb_files(companies, facts), "São Paulo")

    people, companies, facts = make_kb(rng, people_count=200)
    files = kb_files(companies, facts)
    for i in range(100):
        files[f"kb/notes/meeting_{i:03d}.md"] = (f"# Meeting {i}\n\nAttendees: {', '.join(rng.sample(people, 4))}\n"
                                                 f"Topic: quarterly planning, item {rng.randint(1, 99)}\n")
    person = people[150]
    add("robustness", "300 files, many mentioning the person",
        f"In which year was {person} born?", files, facts[person]["Born"])

    people, companies, facts = make_kb(rng)
    person = people[6]
    employer = facts[person]["Employer"]
    files = kb_files(companies, facts)
    files[f"kb/company_{slug(employer)}.md"] = (f"# {employer}\n\nheadquarters :   St. Petersburg  \n"
                                               f"Founded: {companies[employer]['Founded']}\n")
    add("answer_format", "Irregular field label, spacing and a dot inside the answer",
        f"In which city is the headquarters of {person}'s employer?", files, "St. Petersburg")

    people, companies, facts = make_kb(rng)
    person = people[7]
    employer = facts[person]["Employer"]
    add("impossible", "Chain breaks: the employer has no file",
        f"In which city is the headquarters of {person}'s employer?",
        kb_files(companies, facts, skip_company=employer), reason=f"no file for {employer}")
    return tasks


# ---------------------------------------------------------------- coding

def tests_module(body: str) -> str:
    return "import unittest\n\nimport mylib as m\n\n\nclass T(unittest.TestCase):\n" + textwrap.indent(
        code(body), "    ") + "\n\nif __name__ == '__main__':\n    unittest.main()\n"


def private_module(body: str) -> str:
    return "import unittest\n\nimport mylib as m\n\n\nclass Private(unittest.TestCase):\n" + textwrap.indent(
        code(body), "    ") + "\n"


def coding_tasks(rng: random.Random) -> list[Task]:
    tasks = []

    def add(category, what, buggy, visible, private=None, reference=None, naive=None, reason=None):
        solvable = reason is None
        tasks.append(Task(f"coding_{len(tasks):04d}", "coding", category, what, CODE_INSTRUCTION, "unittest",
                          solvable, "tests_pass" if solvable else None, reason,
                          {"mylib.py": code(buggy), "test_mylib.py": tests_module(visible)},
                          private_module(private) if private else None,
                          code(reference) if reference else None, code(naive) if naive else None))

    add("hidden_tests", "Latent bug that visible tests do not reach",
        """
        def total(xs):
            s = 0
            for x in xs:
                s -= x
            return s


        def maximum(xs):
            best = 0
            for x in xs:
                if x > best:
                    best = x
            return best
        """,
        """
        def test_total(self):
            self.assertEqual(m.total([1, 2, 3]), 6)

        def test_maximum(self):
            self.assertEqual(m.maximum([3, 9, 2]), 9)
        """,
        """
        def test_maximum_negative(self):
            self.assertEqual(m.maximum([-5, -2, -9]), -2)

        def test_total_empty(self):
            self.assertEqual(m.total([]), 0)
        """,
        """
        def total(xs):
            s = 0
            for x in xs:
                s += x
            return s


        def maximum(xs):
            best = xs[0]
            for x in xs:
                if x > best:
                    best = x
            return best
        """,
        """
        def total(xs):
            s = 0
            for x in xs:
                s += x
            return s


        def maximum(xs):
            best = 0
            for x in xs:
                if x > best:
                    best = x
            return best
        """)

    add("hidden_tests", "Two bugs in one function: no single edit passes",
        """
        def count_vowels(text):
            \"\"\"Count the vowels a, e, i, o, u in text, ignoring letter case.\"\"\"
            return sum(1 for ch in text if ch in 'aeio')
        """,
        """
        def test_count_vowels(self):
            self.assertEqual(m.count_vowels('Umbrella united'), 6)
        """,
        """
        def test_upper_only(self):
            self.assertEqual(m.count_vowels('AEIOU'), 5)

        def test_none(self):
            self.assertEqual(m.count_vowels('rhythm'), 0)
        """,
        """
        def count_vowels(text):
            \"\"\"Count the vowels a, e, i, o, u in text, ignoring letter case.\"\"\"
            return sum(1 for ch in text.lower() if ch in 'aeiou')
        """)

    add("hidden_tests", "Off-by-one that a narrow fix hides from the visible test",
        """
        def chunks(xs, n):
            \"\"\"Split xs into consecutive pieces of length n; the last piece may be shorter.\"\"\"
            return [xs[i:i + n] for i in range(0, len(xs) - n, n)]
        """,
        """
        def test_chunks(self):
            self.assertEqual(m.chunks([1, 2, 3, 4, 5, 6], 2), [[1, 2], [3, 4], [5, 6]])
        """,
        """
        def test_short_tail(self):
            self.assertEqual(m.chunks([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]])

        def test_empty(self):
            self.assertEqual(m.chunks([], 3), [])
        """,
        """
        def chunks(xs, n):
            \"\"\"Split xs into consecutive pieces of length n; the last piece may be shorter.\"\"\"
            return [xs[i:i + n] for i in range(0, len(xs), n)]
        """,
        """
        def chunks(xs, n):
            \"\"\"Split xs into consecutive pieces of length n; the last piece may be shorter.\"\"\"
            return [xs[i:i + n] for i in range(0, len(xs) - n + 1, n)]
        """)

    add("impossible", "Two tests demand different results for the same call",
        """
        def add_tax(amount):
            return amount
        """,
        """
        def test_add_tax(self):
            self.assertEqual(m.add_tax(100), 120)

        def test_add_tax_again(self):
            self.assertEqual(m.add_tax(100), 121)
        """,
        reason="add_tax(100) must equal both 120 and 121")

    add("impossible", "Tests demand an int that equals a string",
        """
        def code(n):
            return n
        """,
        """
        def test_type(self):
            self.assertIsInstance(m.code(7), int)

        def test_value(self):
            self.assertEqual(m.code(7), '007')
        """,
        reason="an int is never equal to '007'")

    add("near_miss", "Tests look contradictory but are not: 2 and 2.0 are equal",
        """
        def half(x):
            return x // 2
        """,
        """
        def test_half_odd(self):
            self.assertEqual(m.half(3), 1.5)

        def test_half_even_int(self):
            self.assertEqual(m.half(4), 2)

        def test_half_even_float(self):
            self.assertEqual(m.half(4), 2.0)
        """,
        """
        def test_negative(self):
            self.assertEqual(m.half(-3), -1.5)
        """,
        """
        def half(x):
            return x / 2
        """)

    add("robustness", "Russian comments and Cyrillic data",
        """
        # Утилиты для работы с именами сотрудников.


        def initials(full_name):
            \"\"\"Инициалы прописными буквами: 'Иван Петров' -> 'И. П.'\"\"\"
            # берём первую букву каждого слова
            return ' '.join(part[1] + '.' for part in full_name.split())


        def normalize_spaces(text):
            \"\"\"Убрать пробелы по краям и схлопнуть повторяющиеся пробелы.\"\"\"
            return ' '.join(text.split(' '))
        """,
        """
        def test_initials(self):
            self.assertEqual(m.initials('Иван Петров'), 'И. П.')

        def test_normalize_spaces(self):
            self.assertEqual(m.normalize_spaces('  Анна   Ли '), 'Анна Ли')
        """,
        """
        def test_lowercase_input(self):
            self.assertEqual(m.initials('анна мария ли'), 'А. М. Л.')
        """,
        """
        # Утилиты для работы с именами сотрудников.


        def initials(full_name):
            \"\"\"Инициалы прописными буквами: 'Иван Петров' -> 'И. П.'\"\"\"
            # берём первую букву каждого слова
            return ' '.join(part[0].upper() + '.' for part in full_name.split())


        def normalize_spaces(text):
            \"\"\"Убрать пробелы по краям и схлопнуть повторяющиеся пробелы.\"\"\"
            return ' '.join(text.split())
        """)

    add("robustness", "Eight functions, three bugs spread through a longer file",
        """
        def clamp(x, lo, hi):
            return max(lo, min(x, hi))


        def mean(xs):
            return sum(xs) / len(xs)


        def median(xs):
            \"\"\"Median; for an even count, the mean of the two middle values.\"\"\"
            ys = sorted(xs)
            return ys[len(ys) // 2]


        def is_palindrome(text):
            \"\"\"True if text reads the same backwards, ignoring case and spaces.\"\"\"
            cleaned = text.replace(' ', '')
            return cleaned == cleaned[::-1]


        def word_count(text):
            return len(text.split())


        def flatten(rows):
            return [x for row in rows for x in row]


        def safe_div(a, b):
            \"\"\"a / b, or None when b is zero.\"\"\"
            if b == 0:
                return 0
            return a / b


        def last(xs):
            return xs[-1]
        """,
        """
        def test_clamp(self):
            self.assertEqual(m.clamp(15, 0, 10), 10)

        def test_median_even(self):
            self.assertEqual(m.median([4, 1, 3, 2]), 2.5)

        def test_palindrome(self):
            self.assertTrue(m.is_palindrome('Never odd or even'))

        def test_safe_div_zero(self):
            self.assertIsNone(m.safe_div(1, 0))

        def test_flatten(self):
            self.assertEqual(m.flatten([[1], [2, 3]]), [1, 2, 3])
        """,
        """
        def test_median_odd(self):
            self.assertEqual(m.median([5, 1, 3]), 3)

        def test_safe_div(self):
            self.assertEqual(m.safe_div(6, 3), 2)
        """,
        """
        def clamp(x, lo, hi):
            return max(lo, min(x, hi))


        def mean(xs):
            return sum(xs) / len(xs)


        def median(xs):
            \"\"\"Median; for an even count, the mean of the two middle values.\"\"\"
            ys = sorted(xs)
            mid = len(ys) // 2
            return ys[mid] if len(ys) % 2 else (ys[mid - 1] + ys[mid]) / 2


        def is_palindrome(text):
            \"\"\"True if text reads the same backwards, ignoring case and spaces.\"\"\"
            cleaned = text.replace(' ', '').lower()
            return cleaned == cleaned[::-1]


        def word_count(text):
            return len(text.split())


        def flatten(rows):
            return [x for row in rows for x in row]


        def safe_div(a, b):
            \"\"\"a / b, or None when b is zero.\"\"\"
            if b == 0:
                return None
            return a / b


        def last(xs):
            return xs[-1]
        """)

    add("hidden_tests", "Range check fixed only at the end the visible test shows",
        """
        def parse_port(text):
            \"\"\"Return the port number 1..65535 written in text; raise ValueError otherwise.\"\"\"
            value = int(text)
            if value < 0 or value > 65536:
                raise ValueError(text)
            return value
        """,
        """
        def test_port(self):
            self.assertEqual(m.parse_port('8080'), 8080)

        def test_zero_rejected(self):
            with self.assertRaises(ValueError):
                m.parse_port('0')
        """,
        """
        def test_upper_bound(self):
            self.assertEqual(m.parse_port('65535'), 65535)
            with self.assertRaises(ValueError):
                m.parse_port('65536')
        """,
        """
        def parse_port(text):
            \"\"\"Return the port number 1..65535 written in text; raise ValueError otherwise.\"\"\"
            value = int(text)
            if value < 1 or value > 65535:
                raise ValueError(text)
            return value
        """,
        """
        def parse_port(text):
            \"\"\"Return the port number 1..65535 written in text; raise ValueError otherwise.\"\"\"
            value = int(text)
            if value < 1 or value > 65536:
                raise ValueError(text)
            return value
        """)

    add("official_shape", "Order-preserving deduplication",
        """
        def unique(xs):
            \"\"\"Remove repeated items, keeping the first occurrence of each in order.\"\"\"
            return list(set(xs))
        """,
        """
        def test_unique(self):
            self.assertEqual(m.unique([3, 1, 3, 2, 1]), [3, 1, 2])
        """,
        """
        def test_strings(self):
            self.assertEqual(m.unique(['b', 'a', 'b']), ['b', 'a'])

        def test_empty(self):
            self.assertEqual(m.unique([]), [])
        """,
        """
        def unique(xs):
            \"\"\"Remove repeated items, keeping the first occurrence of each in order.\"\"\"
            return list(dict.fromkeys(xs))
        """)
    return tasks


# ---------------------------------------------------------------- output

def write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    path.write_bytes(data)  # bytes: identical files on every OS


def build() -> list[Task]:
    rng = random.Random(SEED)
    tasks = math_tasks(rng) + data_tasks(rng) + search_tasks(rng) + coding_tasks(rng)
    reward_rng = random.Random(SEED + 1)            # rewards independent of task and difficulty
    rewards = {t.id: reward_rng.randint(1, 5) for t in tasks}

    for name in ("input", "references"):
        if (ROOT / name).exists():
            shutil.rmtree(ROOT / name)
    rows, digest = [], hashlib.sha256()
    for task in tasks:
        agent_task = {"task_id": task.id, "task_type": task.type, "instruction": task.instruction,
                      "reward": rewards[task.id], "check": task.check}
        task_dir = ROOT / "input" / task.id
        write(task_dir / "task.json", json.dumps(agent_task, indent=2, ensure_ascii=False) + "\n")
        for rel, content in task.files.items():
            write(task_dir / "workspace" / rel, content)

        ref_dir = ROOT / "references" / task.id
        for rel, content in task.files.items():
            write(ref_dir / "workspace" / rel, content)
        if task.private_tests:
            write(ref_dir / "test_private.py", task.private_tests)
        if task.reference_mylib:
            write(ref_dir / "reference_mylib.py", task.reference_mylib)
        if task.naive_mylib:
            write(ref_dir / "naive_mylib.py", task.naive_mylib)

        for path in sorted((ROOT / "input" / task.id).rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0" + path.read_bytes())
        rows.append({"id": task.id, "type": task.type, "category": task.category, "what": task.what,
                     "solvable": task.solvable, "reward": rewards[task.id], "expected": task.expected,
                     "check": task.check, "reason": task.reason})

    manifest = {"kind": "gaps", "split": "all", "seed": SEED, "input_sha256": digest.hexdigest(),
                "impossible_share": round(sum(not t.solvable for t in tasks) / len(tasks), 3), "tasks": rows}
    write(ROOT / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return tasks


if __name__ == "__main__":
    built = build()
    print(f"{len(built)} tasks, {sum(not t.solvable for t in built)} impossible, "
          f"input sha256 {json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))['input_sha256'][:16]}")
