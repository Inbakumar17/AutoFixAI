"""Benchmark corpus.

Each Case has a buggy program and a hand-written *reference* solution.  The
reference's output is the oracle: a repair only counts as correct when the
repaired program runs, prints exactly what the reference prints, and leaves no
static issues behind.

Honest caveats (also stated in RESULTS.md):
  * The corpus is small and written by the tool's author, so it is a regression
    benchmark, not independent evidence of real-world performance.
  * For "guard" cases (division by zero, missing dict key) the reference accepts
    ``None`` as the result - one of several defensible intents.
  * ``unsupported`` cases are bug classes the tool does NOT claim to handle; they
    are included so the overall score is not inflated.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    buggy: str
    reference: str


CASES: list[Case] = []


def add(id, category, buggy, reference):
    CASES.append(Case(id, category, buggy.lstrip("\n"), reference.lstrip("\n")))


# --------------------------------------------------------------- typos
add("typo-function", "undefined-name", """
def total(xs):
    return sum(xs)

print(totl([1, 2, 3]))
""", """
def total(xs):
    return sum(xs)

print(total([1, 2, 3]))
""")

add("typo-parameter", "undefined-name", """
def area(width, height):
    return width * hieght

print(area(2, 3))
""", """
def area(width, height):
    return width * height

print(area(2, 3))
""")

add("typo-builtin", "undefined-name", """
prnt("hello")
""", """
print("hello")
""")

add("typo-loop-variable", "undefined-name", """
def squares(n):
    out = []
    for value in range(n):
        out.append(valu * valu)
    return out

print(squares(4))
""", """
def squares(n):
    out = []
    for value in range(n):
        out.append(value * value)
    return out

print(squares(4))
""")

add("typo-assigned-call", "undefined-name", """
def greet(name):
    return "Hello, " + name

message = gret("Ada")
print(message)
""", """
def greet(name):
    return "Hello, " + name

message = greet("Ada")
print(message)
""")

# --------------------------------------------------------- missing import
add("import-os", "missing-import", """
print(os.path.basename("/tmp/a.txt"))
""", """
import os

print(os.path.basename("/tmp/a.txt"))
""")

add("import-math", "missing-import", """
def hyp(a, b):
    return math.sqrt(a * a + b * b)

print(hyp(3, 4))
""", """
import math


def hyp(a, b):
    return math.sqrt(a * a + b * b)

print(hyp(3, 4))
""")

add("import-json", "missing-import", """
print(json.dumps({"a": 1}))
""", """
import json

print(json.dumps({"a": 1}))
""")

add("import-sys", "missing-import", """
print(sys.version_info[0] >= 3)
""", """
import sys

print(sys.version_info[0] >= 3)
""")

add("import-datetime", "missing-import", """
print(datetime.date(2020, 1, 2).isoformat())
""", """
import datetime

print(datetime.date(2020, 1, 2).isoformat())
""")

# --------------------------------------------------------- mutable default
add("mutable-list", "mutable-default", """
def add_item(item, bucket=[]):
    bucket.append(item)
    return bucket

print(add_item(1))
print(add_item(2))
""", """
def add_item(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket

print(add_item(1))
print(add_item(2))
""")

add("mutable-dict", "mutable-default", """
def count(word, seen={}):
    seen[word] = seen.get(word, 0) + 1
    return seen[word]

print(count("a"))
print(count("a"))
""", """
def count(word, seen=None):
    if seen is None:
        seen = {}
    seen[word] = seen.get(word, 0) + 1
    return seen[word]

print(count("a"))
print(count("a"))
""")

add("mutable-kwonly-set", "mutable-default", """
def tag(name, *, tags=set()):
    tags.add(name)
    return len(tags)

print(tag("x"))
print(tag("y"))
""", """
def tag(name, *, tags=None):
    if tags is None:
        tags = set()
    tags.add(name)
    return len(tags)

print(tag("x"))
print(tag("y"))
""")

# --------------------------------------------------------- lint-level
add("unused-import", "unused", """
import os

print("ok")
""", """
print("ok")
""")

add("unused-variable-pure", "unused", """
def f(x):
    debug = 0
    return x + 1

print(f(1))
""", """
def f(x):
    return x + 1

print(f(1))
""")

add("unused-variable-call", "unused", """
def f(x):
    tmp = print("side effect")
    return x

print(f(2))
""", """
def f(x):
    print("side effect")
    return x

print(f(2))
""")

add("unused-import-partial", "unused", """
import os, sys

print(sys.maxsize > 0)
""", """
import sys

print(sys.maxsize > 0)
""")

# --------------------------------------------------------- zero division
add("zero-literal-param", "zero-division", """
def ratio(part, whole):
    return part / 0

print(ratio(1, 4))
""", """
def ratio(part, whole):
    if whole == 0:
        return None
    return part / whole

print(ratio(1, 4))
""")

add("zero-named-divisor", "zero-division", """
def safe_div(a, b):
    return a / b

print(safe_div(6, 3))
print(safe_div(1, 0))
""", """
def safe_div(a, b):
    if b == 0:
        return None
    return a / b

print(safe_div(6, 3))
print(safe_div(1, 0))
""")

add("zero-empty-average", "zero-division", """
def average(values):
    total = sum(values)
    count = len(values)
    return total / count

print(average([2, 4]))
print(average([]))
""", """
def average(values):
    total = sum(values)
    count = len(values)
    if count == 0:
        return None
    return total / count

print(average([2, 4]))
print(average([]))
""")

add("zero-modulo-literal", "zero-division", """
def wrap(n, k):
    return n % 0

print(wrap(7, 3))
""", """
def wrap(n, k):
    if k == 0:
        return None
    return n % k

print(wrap(7, 3))
""")

# --------------------------------------------------------- index errors
add("index-range-plus-one", "index-error", """
def total(nums):
    s = 0
    for i in range(len(nums) + 1):
        s += nums[i]
    return s

print(total([1, 2, 3]))
""", """
def total(nums):
    s = 0
    for i in range(len(nums)):
        s += nums[i]
    return s

print(total([1, 2, 3]))
""")

add("index-while-lte", "index-error", """
def show(items):
    i = 0
    out = []
    while i <= len(items):
        out.append(items[i])
        i += 1
    return out

print(show([4, 5]))
""", """
def show(items):
    i = 0
    out = []
    while i < len(items):
        out.append(items[i])
        i += 1
    return out

print(show([4, 5]))
""")

add("index-len-as-index", "index-error", """
data = [10, 20, 30]
print(data[len(data)])
""", """
data = [10, 20, 30]
print(data[len(data) - 1])
""")

add("index-range-from-one", "index-error", """
xs = [3, 1, 2]
for i in range(1, len(xs) + 1):
    print(xs[i])
""", """
xs = [3, 1, 2]
for i in range(1, len(xs)):
    print(xs[i])
""")

# --------------------------------------------------------- key errors
add("key-missing-toplevel", "key-error", """
ages = {"ann": 30}
print(ages["bob"])
""", """
ages = {"ann": 30}
print(ages.get("bob"))
""")

add("key-in-function", "key-error", """
config = {"host": "x"}


def port():
    return config["port"]

print(port())
""", """
config = {"host": "x"}


def port():
    return config.get("port")

print(port())
""")

add("key-two-subscripts", "key-error", """
prices = {"a": 1}
print(prices["a"], prices["c"])
""", """
prices = {"a": 1}
print(prices["a"], prices.get("c"))
""")

# --------------------------------------------------------- string concat
add("concat-str-plus-int", "str-concat", """
count = 3
print("Count: " + count)
""", """
count = 3
print("Count: " + str(count))
""")

add("concat-int-plus-str", "str-concat", """
count = 3
print(count + " items")
""", """
count = 3
print(str(count) + " items")
""")

add("concat-chain", "str-concat", """
a = 1
b = 2
print("a=" + a + ", b=" + b)
""", """
a = 1
b = 2
print("a=" + str(a) + ", b=" + str(b))
""")

add("concat-call-result", "str-concat", """
print("Sum: " + sum([1, 2]))
""", """
print("Sum: " + str(sum([1, 2])))
""")

# --------------------------------------------------------- is literal
add("is-string", "is-literal", """
mode = "fast"
if mode is "fast":
    print("go")
""", """
mode = "fast"
if mode == "fast":
    print("go")
""")

add("is-not-int", "is-literal", """
n = 1000
if n is not 5:
    print("different")
""", """
n = 1000
if n != 5:
    print("different")
""")

# --------------------------------------------------------- unsupported (honest)
add("UNSUP-syntax-colon", "unsupported", """
def f()
    return 1

print(f())
""", """
def f():
    return 1

print(f())
""")

add("UNSUP-logic-operator", "unsupported", """
def add(a, b):
    return a - b

print(add(2, 3))
""", """
def add(a, b):
    return a + b

print(add(2, 3))
""")

add("UNSUP-logic-range", "unsupported", """
print(sum(range(1, 5)))
""", """
print(sum(range(1, 6)))
""")

add("UNSUP-none-attribute", "unsupported", """
def find(xs, t):
    for x in xs:
        if x == t:
            return x

print(find([1, 2], 3).bit_length())
""", """
def find(xs, t):
    for x in xs:
        if x == t:
            return x
    return 0

print(find([1, 2], 3).bit_length())
""")

add("UNSUP-infinite-loop", "unsupported", """
i = 0
while i < 3:
    print(i)
""", """
i = 0
while i < 3:
    print(i)
    i += 1
""")

add("UNSUP-recursion", "unsupported", """
def fact(n):
    return n * fact(n - 1)

print(fact(3))
""", """
def fact(n):
    if n <= 1:
        return 1
    return n * fact(n - 1)

print(fact(3))
""")

# --------------------------------------------------------- controls (already correct)
CONTROLS: list[Case] = []


def control(id, code):
    CONTROLS.append(Case(id, "control", code.lstrip("\n"), code.lstrip("\n")))


control("ctl-similar-names", """
def calculate(a):
    return a


def calculate_total(a):
    return calculate(a) * 2


print(calculate_total(2))
""")
control("ctl-name-in-string", """
def calculate():
    return 1


print("calculte")  # a typo inside a string must stay
print(calculate())
""")
control("ctl-import-used", """
import os

print(os.sep in "/\\\\")
""")
control("ctl-none-default", """
def f(x, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(x)
    return bucket


print(f(1))
""")
control("ctl-dict-get", """
d = {"a": 1}
print(d.get("b"), "a" in d)
""")
control("ctl-correct-range", """
xs = [1, 2, 3]
total = 0
for i in range(len(xs)):
    total += xs[i]
print(total)
""")
control("ctl-str-concat-ok", """
n = 3
print("n=" + str(n) + "!")
""")
control("ctl-guarded-division", """
def ratio(a, b):
    if b == 0:
        return None
    return a / b


print(ratio(1, 2), ratio(1, 0))
""")
control("ctl-module-level-unused", """
debug = True
print("running")
""")
control("ctl-is-none", """
x = None
if x is None:
    print("none")
""")
control("ctl-class", """
class Counter:
    def __init__(self):
        self.n = 0

    def inc(self):
        self.n += 1
        return self.n


c = Counter()
c.inc()
print(c.inc())
""")
