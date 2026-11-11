"""Reproducible, host-only fixtures. No API calls or agent imports."""
from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import math
import random
import textwrap
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED = 631907
CASES = []
TAIL = (' Work only inside the current directory. When you are done, write ONLY '
        'the final answer to the file answer.txt in the current directory.')


def csv_text(columns, rows, delimiter=','):
    out = io.StringIO(newline='')
    writer = csv.writer(out, delimiter=delimiter, lineterminator='\n')
    writer.writerow(columns)
    writer.writerows(rows)
    return out.getvalue()


def js(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def add(kind, family, title, difficulty, prompt, expected, files=None, *, why,
        check='exact_int', solvable=True, reference=None, private=None):
    CASES.append(dict(type=kind, family=family, title=title, difficulty=difficulty,
                      prompt=prompt, expected=str(expected), files=files or {},
                      why=why, check=check, solvable=solvable,
                      reference=reference, private=private))


def maths():
    def put(family, title, level, prompt, expected, files=None, why='', **kw):
        add('math', family, title, level, prompt, expected, files, why=why, **kw)

    put('unit_conversion', 'Единицы измерения и остаток', 'easy',
        'A tank contains 2.75 cubic metres of water. Exactly 38 containers of 12.5 litres each are filled from it. '
        'How many millilitres remain? Return an integer.', 2275000,
        why='2,750,000 - 38 * 12,500 = 2,275,000 millilitres.')
    put('piecewise_tariff', 'Тариф со ступенями и округлением', 'easy',
        'Monthly consumption is 237 units. The first 100 cost 17 cents each, the next 100 cost 23 cents each, '
        'and the rest cost 31 cents each. Add a fixed charge of 450 cents, then apply a 7.5% tax to the whole bill. '
        'Round the final bill to the nearest cent, ties upward. Return integer cents.',
        int((Decimal(100*17+100*23+37*31+450)*Decimal('1.075')).quantize(Decimal(1), rounding=ROUND_HALF_UP)),
        why='Tax applies after the fixed charge; the untaxed bill is 5597 cents.')
    start = date(2024, 2, 23)
    holidays = {date(2024, 2, 26), date(2024, 3, 8)}
    day, count = start, 0
    while count < 12:
        day += timedelta(days=1)
        if day.weekday() < 5 and day not in holidays:
            count += 1
    assert str(day) == '2024-03-14'
    put('business_calendar', 'Рабочие дни через високосный февраль', 'medium',
        'A request arrives on 2024-02-23. Its deadline is the 12th business day strictly after arrival. '
        'Business days are Monday through Friday except 2024-02-26 and 2024-03-08. Return the date as YYYY-MM-DD.',
        day, why='The counted days are Feb 27,28,29; Mar 1,4,5,6,7,11,12,13,14.', check='exact_str')
    valid = [n for n in range(1, 2000) if n % 7 == 3 and n % 11 == 8 and n % 13 == 5]
    put('modular_schedule', 'Совпадение периодических событий', 'medium',
        'Find the smallest positive integer n such that n modulo 7 is 3, n modulo 11 is 8, '
        'and n modulo 13 is 5. Return n.', min(valid), why='Enumerated one complete period of 1001 integers.')
    prob = Fraction(math.comb(7, 2)*math.comb(5, 1), math.comb(12, 3))
    assert prob == Fraction(21, 44)
    put('sampling_probability', 'Вероятность без возвращения', 'easy',
        'A bag has 7 red and 5 blue tokens. Three distinct tokens are drawn uniformly without replacement. '
        'What is the probability of exactly two red tokens? Return a reduced fraction numerator/denominator.',
        prob, why='C(7,2)*C(5,1)/C(12,3) = 21/44.', check='exact_str')
    weights = [2, 5, 9, 12]
    counts = [3, 2, 2, 1]
    ways = sum(sum(x*w for x,w in zip(xs, weights)) == 26
               for xs in itertools.product(*(range(n+1) for n in counts)))
    put('bounded_change', 'Число способов с ограниченным запасом', 'medium',
        'Available coins: three of value 2, two of value 5, two of value 9, and one of value 12. '
        'How many distinct count-vectors give total 26? Coins of the same value are indistinguishable; '
        'order does not matter. Return an integer.', ways, why='Exhaustively counted the 4*3*3*2 possible count-vectors.')
    points = [(0,0),(8,0),(8,3),(5,3),(5,7),(0,7)]
    area2 = abs(sum(x*v-y*u for (x,y),(u,v) in zip(points, points[1:]+points[:1])))
    assert area2 == 88
    put('polygon_area', 'Площадь невыпуклого контура', 'easy',
        'A simple polygon has consecutive vertices (0,0), (8,0), (8,3), (5,3), (5,7), (0,7). '
        'Return twice its area as an integer.', area2, why='An 8*7 rectangle minus a 3*4 notch has area 44.')
    jobs = [(0,4,9),(1,3,8),(3,5,8),(4,7,10),(5,8,12),(7,9,7),(8,11,11),(9,12,13),(11,13,5)]
    feasible = []
    for bits in itertools.product([0,1], repeat=len(jobs)):
        chosen = [j for j,b in zip(jobs,bits) if b]
        if all(a[1] <= b[0] or b[1] <= a[0] for a,b in itertools.combinations(chosen,2)):
            feasible.append(sum(j[2] for j in chosen))
    put('weighted_intervals', 'Выбор непересекающихся заказов', 'hard',
        'jobs.csv lists jobs with start, end and profit. Select any subset with no overlap on one machine. '
        'Intervals are half-open [start,end), so touching endpoints are allowed. Return the maximum total profit.',
        max(feasible), {'jobs.csv':csv_text(['start','end','profit'],jobs)}, why='Exhaustive verification over all 512 subsets.')
    matrix = [[8,3,9,6,7],[5,7,4,8,6],[6,9,5,3,8],[7,6,8,5,4],[9,4,6,7,5]]
    best = min(sum(matrix[i][p[i]] for i in range(5)) for p in itertools.permutations(range(5)))
    put('assignment', 'Взаимно однозначное назначение', 'hard',
        'costs.json is a 5 by 5 matrix: row i is worker i, column j is job j. '
        'Each worker must receive exactly one job and each job exactly one worker. Return minimum total cost.',
        best, {'costs.json':js(matrix)}, why='All 120 bijections checked.')
    # Expected hitting time: E0=1+(E0+E1)/2; E1=1+E0/2, hence E0=6.
    put('expected_wait', 'Ожидаемое время до серии событий', 'hard',
        'A fair coin is tossed repeatedly. Starting with no previous toss, how many tosses are expected '
        'until two consecutive heads first occur? Return an integer.', 6,
        why='E0=1+(E0+E1)/2 and E1=1+E0/2 give E0=6.')
    put('inclusion_exclusion', 'Объединение пересекающихся множеств', 'medium',
        'In a survey, 43 people use A, 37 use B and 29 use C. Intersections including triple users are '
        '|A and B|=17, |A and C|=11, |B and C|=13. Nine use all three. '
        'How many people use at least one? Return an integer.', 77,
        why='43+37+29-17-11-13+9=77.')
    # Inclusion-exclusion for monotone paths avoiding two blocked cells.
    def paths(a,b):
        dx,dy=b[0]-a[0],b[1]-a[1]
        return math.comb(dx+dy,dx) if min(dx,dy)>=0 else 0
    a,b=(3,2),(6,5)
    count = paths((0,0),(9,7))-paths((0,0),a)*paths(a,(9,7))-paths((0,0),b)*paths(b,(9,7))+paths((0,0),a)*paths(a,b)*paths(b,(9,7))
    dp = {(0,0):1}
    for x in range(10):
        for y in range(8):
            if (x,y)!=(0,0): dp[x,y]=0 if (x,y) in (a,b) else dp.get((x-1,y),0)+dp.get((x,y-1),0)
    assert count == dp[9,7]
    put('lattice_paths', 'Подсчёт маршрутов с препятствиями', 'hard',
        'On the integer grid, move from (0,0) to (9,7), each step either (1,0) or (0,1). '
        'Never visit (3,2) or (6,5). Return the number of distinct paths.', count,
        why='Independent inclusion-exclusion and dynamic programming agree.')
    balance = Decimal('1000.00')
    for _ in range(17): balance=(balance*Decimal('1.0065')-Decimal('37.25')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    put('amortization', 'Порядок начисления процентов и платежей', 'medium',
        'A loan starts at 1000.00 dollars. Each month multiply the current balance by 1.0065, subtract '
        '37.25 dollars, then round to cents using nearest with ties away from zero. Perform exactly 17 months. '
        'Return remaining balance in integer cents.', int(balance*100), why='17 explicitly ordered Decimal updates, rounding once per month.')
    edges = [('S','A',7),('S','B',4),('B','A',2),('A','C',3),('B','C',8),('B','D',5),('C','T',6),('D','T',3),('C','D',1)]
    # Every simple path, and one optional half-price edge rounded down.
    costs=[]
    def walk(node, visited, ws):
        if node=='T':
            costs.append(sum(ws)); costs.extend(sum(ws)-w+w//2 for w in ws); return
        for u,v,w in edges:
            if u==node and v not in visited: walk(v, visited|{v}, ws+[w])
    walk('S',{'S'},[])
    put('discounted_route', 'Маршрут с одноразовой скидкой', 'hard',
        'roads.csv contains directed edges with positive integer tolls. Travel from S to T. '
        'At most once, a coupon may replace one edge toll w by floor(w/2). Return the minimum total toll.',
        min(costs), {'roads.csv':csv_text(['from','to','toll'],edges)}, why='All simple paths and all possible coupon positions enumerated; positive tolls make cycles unnecessary.')
    # Unique max-min integer allocation with capacity and mandatory lower bounds.
    combos=[(x,y,z) for x in range(2,20) for y in range(1,20) for z in range(1,20) if 3*x+4*y+5*z<=59]
    optimum=max(min(4*x,5*y,7*z) for x,y,z in combos)
    put('bottleneck_allocation', 'Распределение бюджета по узкому месту', 'hard',
        'Choose integers x>=2, y>=1, z>=1 with 3*x+4*y+5*z<=59. Output the maximum possible '
        'value of min(4*x,5*y,7*z).', optimum, why='Enumerated all feasible triples; each variable is below 20 by the budget constraint.')
    put('missing_rate', 'Недостаточные данные о начислениях', 'medium',
        'A balance was 5000 cents on Monday and 5400 cents on Friday. There was exactly one deposit on Wednesday '
        'and daily interest on Tuesday through Friday. The interest rate and deposit amount are not recorded. '
        'What was the Wednesday deposit in cents?', 'IMPOSSIBLE',
        why='At zero interest the deposit is 400; at positive interest it is lower. Both fit the stated totals.',
        solvable=False)


def data_tasks():
    rng=random.Random(SEED+1)
    def put(family,title,level,prompt,expected,files,why,**kw):
        add('data_analysis',family,title,level,prompt,expected,files,why=why,**kw)
    rows=[(i, rng.choice(['east','west','north']),rng.randint(1,12),rng.randint(-3,25)) for i in range(1,601)]
    expected=sum(u for _,r,m,u in rows if r=='west' and 4<=m<=9)
    put('filter_sum','Фильтрация с отрицательными значениями','easy',
        'In sales.csv, sum units for region west and month 4 through 9 inclusive. Negative units are returns '
        'and must be included as written. Return an integer.', expected,
        {'sales.csv':csv_text(['id','region','month','units'],rows)}, 'Direct row filter and signed sum.')
    rows=[('A','2026-01-01',10),('B','2026-01-02',3),('A','2026-01-03',4),('B','2026-01-01',12),('C','2026-01-01',7),('C','2026-01-04',0)]
    put('latest_snapshot','Последнее состояние вместо суммы','easy',
        'stock.csv contains complete stock snapshots, not changes. Keep the latest date for each product. '
        'Return the sum of those latest stocks.',7,{'stock.csv':csv_text(['product','date','stock'],rows)},
        'Latest values are A=4, B=3, C=0; sum=7.')
    prices=[('A','2026-01-01',100),('A','2026-02-01',140),('B','2026-01-01',70),('B','2026-03-01',90)]
    orders=[(1,'A','2026-01-20',3),(2,'A','2026-02-01',2),(3,'B','2026-02-20',5),(4,'B','2026-03-01',1)]
    put('asof_join','Соединение по действующей на дату цене','medium',
        'For each order in orders.csv use the price for its product with the greatest effective date '
        'not later than the order date, including equal dates, from prices.csv. Multiply by quantity and '
        'sum all orders. Prices are integer cents. Return total integer cents.',1020,
        {'orders.csv':csv_text(['id','product','date','quantity'],orders),'prices.csv':csv_text(['product','effective','cents'],prices)},
        '300+280+350+90=1020.')
    users=[(f'U{i:03}', '2026-01' if i<80 else '2026-02') for i in range(120)]
    events=[(f'U{i:03}',month) for i in range(120) for month in ('2026-02','2026-03') if (i+(0 if month=='2026-02' else 1))%3==0]
    events += events[:15]
    expected=len({u for u,m in events if m=='2026-03' and int(u[1:])<80})
    put('cohort_retention','Когорты и уникальные пользователи','medium',
        'users.csv gives signup month. events.csv gives activity months and may contain duplicates. '
        'How many distinct users who signed up in 2026-01 were active in 2026-03? Return an integer.',expected,
        {'users.csv':csv_text(['user','signup_month'],users),'events.csv':csv_text(['user','month'],events)},
        'Set intersection of January signup IDs and March active IDs, not event count.')
    rows=[('one','SALE','12,50'),('two',' sale ','2,00'),('one','refund','3,25'),('two','note\nignored','900,00'),('one','sale','-1,00')]
    put('quoted_decimal','CSV с кавычками и десятичной запятой','easy',
        'ledger.csv is comma-delimited CSV with standard quoting. Amounts use comma decimals. '
        'Trim and lowercase kind: sale adds amount, refund subtracts amount; ignore other kinds. '
        'Return total net integer cents across all accounts.',1025,
        {'ledger.csv':csv_text(['account','kind','amount'],rows)}, '1250+200-325-100=1025; embedded newline is inside one quoted field.')
    rows=[(1,'2026-03-01T00:30:00+02:00',4),(2,'2026-02-28T23:40:00-03:00',7),(3,'2026-03-01T22:15:00-04:00',8),(4,'2026-03-01T01:05:00Z',3)]
    put('utc_boundaries','Часовые пояса на границе суток','medium',
        'events.csv timestamps include their UTC offsets. Sum amount for events whose UTC calendar date '
        'is 2026-03-01. Return an integer.',10,{'events.csv':csv_text(['id','timestamp','amount'],rows)},
        'Only rows 2 and 4 fall on March 1 in UTC.')
    rows=[('A',10,1),('A',None,9),('A',20,3),('B',30,2),('B',50,0),('B',40,2)]
    put('weighted_missing','Взвешенное среднее с пропусками','medium',
        'measurements.csv has group, value, weight. Empty value means missing: exclude both its value and its '
        'weight. Compute the weighted mean for group A. Return exactly two decimal places, rounding nearest '
        'with ties away from zero.', '17.50',{'measurements.csv':csv_text(['group','value','weight'],rows)},
        '(10*1+20*3)/(1+3)=17.50.',check='exact_str')
    records=[]
    for i in range(220):
        records.append({'id':i,'state':'paid' if i%4 else 'void','lines':[{'qty':i%5+1,'cents':17},{'qty':2,'cents':i%13}]})
    total=sum(sum(l['qty']*l['cents'] for l in r['lines']) for r in records if r['state']=='paid')
    put('nested_jsonl','Агрегация вложенных строк JSONL','hard',
        'orders.jsonl has one JSON order per line. For orders with state paid, sum qty*cents across all '
        'their lines. Ignore void orders entirely. Return integer cents.',total,
        {'orders.jsonl':''.join(json.dumps(r)+'\n' for r in records)},'Nested sum over paid orders, not a flat CSV schema.')
    rows=[('a',0),('a',10),('a',40),('a',71),('b',0),('b',30),('b',61),('b',62),('c',100)]
    rng.shuffle(rows)
    put('session_gaps','Сессии на границе таймаута','hard',
        'activity.csv contains user and minute, in arbitrary row order. For each user sort by minute. '
        'The first event starts a session. Each subsequent event starts a new session only when its gap '
        'from the previous event is strictly greater than 30 minutes. Return total sessions across users.',5,
        {'activity.csv':csv_text(['user','minute'],rows)},'a has 2 sessions, b has 2, c has 1; exactly 30 stays in the same session.')
    obs=[(i,rng.randint(-10,50)) for i in range(100)]
    maxsum=max(sum(v for _,v in obs[i:i+7]) for i in range(len(obs)-6))
    put('rolling_window','Лучшее полное скользящее окно','hard',
        'series.csv has one observation for each day 0 through 99. Find the largest sum in any seven '
        'consecutive days. Use only complete seven-day windows; negative values are valid. Return an integer.',maxsum,
        {'series.csv':csv_text(['day','value'],list(reversed(obs)))},'94 complete windows checked against original chronological values.')
    vals=[1,2,3,5,8,13,21,34,55,89]
    put('nearest_rank','Перцентиль с заданным определением','easy',
        'latency.tsv is tab-separated. Compute the 80th percentile of milliseconds using nearest rank: '
        'sort ascending and choose the element at one-based rank ceil(0.8*N). Return an integer.',34,
        {'latency.tsv':csv_text(['request','milliseconds'],enumerate(reversed(vals)),delimiter='\t')},
        'Rank 8 among 10 observations is 34.')
    purchases=[('A',i) for i in range(30)]+[('B',i) for i in range(20,50)]+[('C',i) for i in range(0,50,3)]
    put('anti_join','Поиск отсутствующих связей','hard',
        'purchases.csv lists product and customer ID, with possible duplicates. Count distinct customers '
        'who bought A and B but never C. Return an integer.',7,
        {'purchases.csv':csv_text(['product','customer'],purchases+purchases[:7])},
        'A intersect B = 20..29; remove 21,24,27, leaving 7.')
    rows=[('a',1,10),('b',1,20),('a',2,8),('c',1,9),('b',2,0),('a',1,10)]
    put('revision_dedup','Дубликаты и исправления записей','medium',
        'readings.csv may repeat identical rows. Each (meter,revision) identifies a reading. For each meter '
        'keep only its greatest revision, then sum value. A zero reading is valid. Return an integer.',17,
        {'readings.csv':csv_text(['meter','revision','value'],rows)},'a revision 2 -> 8; b revision 2 -> 0; c -> 9.')
    rows=[('root','',2),('A','root',3),('B','root',5),('C','A',7),('D','A',11),('E','B',13),('F','C',17)]
    put('recursive_hierarchy','Агрегация по всем потомкам','hard',
        'org.csv describes a rooted tree with each node appearing once. Return the sum of value for A '
        'and ALL of its descendants at any depth.',38,{'org.csv':csv_text(['node','parent','value'],rows)},
        'A,C,D,F have values 3+7+11+17=38.')
    balances={'a':10,'b':0,'c':7}; transactions=[(1,'a','b',8),(2,'b','c',9),(3,'c','a',4),(4,'b','a',3),(5,'a','c',10)]
    state=dict(balances)
    for _,src,dst,amt in transactions:
        if state[src]>=amt: state[src]-=amt; state[dst]+=amt
    assert sum(state.values())==17
    put('conditional_ledger','Последовательные переводы и отказ','hard',
        'accounts.csv gives initial integer balances. Process transfers.csv by ascending sequence. '
        'Apply a transfer only if the sender currently has at least amount; otherwise ignore it entirely. '
        'Return account a final balance.',state['a'],
        {'accounts.csv':csv_text(['account','balance'],balances.items()),'transfers.csv':csv_text(['sequence','sender','recipient','amount'],list(reversed(transactions)))},
        'Balances are mutated after accepted transfers; final a=9,b=5,c=3 and total stays 17.')
    put('missing_join_key','Неоднозначное соединение данных','medium',
        'orders.csv lists order ID and customer name. customers.csv lists customer ID, name and city. '
        'What is the city of the customer who placed order O7? Return only the city name.', 'IMPOSSIBLE',
        {'orders.csv':csv_text(['order','name'],[('O7','Alex Lee')]),
         'customers.csv':csv_text(['id','name','city'],[('C1','Alex Lee','Oslo'),('C2','Alex Lee','Lima')])},
        'The order has no ID to distinguish two same-name customers in different cities.',check='exact_str',solvable=False)


def searches():
    def put(family,title,level,prompt,expected,docs,why,**kw):
        add('search',family,title,level,prompt,expected,{'kb/'+p:t+'\n' for p,t in docs.items()},why=why,check='exact_str',**kw)
    put('entity_disambiguation','Тёзки и идентификатор','easy',
        'Using kb/, find the birth year of engineer Mara Vale with employee ID E41. Return only the year.',1986,
        {'people.md':'E14: Mara Vale, historian, born 1973.\nE41: Mara Vale, engineer, born 1986.\nE91: Mira Vale, engineer, born 1989.'},
        'people.md: exact employee ID E41, not the first name match.')
    put('alias_chain','Цепочка старых названий','easy',
        'Using kb/, what is the present legal name of the company formerly called North Kite? Return only its name.',
        'Solace Works',{'renames/early.md':'North Kite was renamed Beacon Labs in 2004.',
                        'renames/later.md':'Beacon Labs was renamed Solace Works in 2019. No subsequent name change has occurred.',
                        'other.md':'North Kites (plural) is now Orbit Ltd.'},'Follow both renames; plural North Kites is another entity.')
    put('effective_vs_published','Дата публикации и дата вступления','medium',
        'According to kb/, who held the role of director of Atlas on 2026-04-15? Appointments take effect '
        'on the stated effective date, not publication date. Return only the full name.', 'Ivo Reed',
        {'notices.md':'Published 2026-02-01: Ivo Reed appointed Atlas director effective 2026-03-01.\n'
                       'Published 2026-04-02: Nia Cole appointed Atlas director effective 2026-05-01.\n'
                       'Published 2025-01-01: Eli Moss appointed Atlas director effective 2025-01-01.'},
        'The Nia notice is already published but not yet effective.')
    put('source_precedence','Официальный реестр и противоречащие копии','medium',
        'Using kb/, give the registered seat of Meridian Trust. The registry is authoritative; directory '
        'and news pages may be stale. Return only the city.', 'Ghent',
        {'registry/entry.md':'Meridian Trust (MT-19): registered seat Ghent, current filing.',
         'news/article.md':'Meridian Trust reportedly moved its offices to Berlin.',
         'directory.md':'Meridian Trust: registered seat Prague. Copied from a 2009 directory.'},
        'Registered seat differs from offices; registry/entry.md controls.')
    put('set_intersection','Поиск с несколькими обязательными условиями','easy',
        'Using kb/, which project is BOTH funded by Helios AND based in Bergen AND active? Return only its project ID.',
        'P14',{'projects.md':'P11: Helios; Bergen; closed.\nP12: Selene; Bergen; active.\nP13: Helios; Oslo; active.\nP14: Helios; Bergen; active.'},
        'Only P14 satisfies all three predicates.')
    put('numeric_versions','Числовые версии вместо лексикографических','medium',
        'Using kb/, what port does the highest numeric approved version of service Kite specify? '
        'Ignore drafts. Return only the integer port.', '8410',
        {'v9.md':'Kite version 9, approved, port 8409.', 'v10.md':'Kite version 10, approved, port 8410.',
         'v11.md':'Kite version 11, draft, port 8411.','v2.md':'Kite version 2, approved, port 8402.'},
        'Approved numeric version 10 is newer than 9; draft 11 excluded.')
    put('multihop_ownership','Несколько связей между разными документами','hard',
        'Using kb/, in which city is the owner of the publisher of journal Amber Review registered? Return only the city.',
        'Turku',{'journals.md':'Amber Review is published by Cedar Press. Amber Weekly is published by Elm Press.',
         'publishers.md':'Cedar Press is owned by Moss Holdings. Elm Press is owned by Cedar Group.',
         'register.md':'Moss Holdings: registered Turku. Cedar Group: registered Dublin. Cedar Press: office Rome.'},
        'Amber Review -> Cedar Press -> Moss Holdings -> Turku, not publisher office.')
    put('policy_exception','Исключение к правилу и его границы','hard',
        'Using only kb/, how many days of notice must a contractor in grade G2 give when leaving during '
        'their first 60 days? Return only the integer number of days.',7,
        {'policy/base.md':'Employees must give 30 days notice. Contractors must give 21 days notice.',
         'policy/addendum.md':'Contractors in grades G1 and G2 during their first 60 days give 7 days notice. '
                              'This addendum overrides the contractor notice rule for these people.',
         'faq.md':'Employees in G2 probation give 14 days notice. This FAQ applies only to employees.'},
        'Contractor exception applies; employee FAQ does not.')
    put('event_reconstruction','Восстановление порядка событий','medium',
        'Using kb/, which station did cargo C8 visit immediately before its first arrival at North? '
        'Order by event time, not file name or reporting time. Return only the station name.', 'West',
        {'events/a.md':'C8 event 2026-04-01T08:00Z at South, reported 10:00Z.',
         'events/b.md':'C8 event 2026-04-01T09:00Z at North, reported 09:01Z.',
         'events/c.md':'C8 event 2026-04-01T08:40Z at West, reported 11:00Z.',
         'events/d.md':'C8 event 2026-04-01T09:30Z at East, reported 09:31Z.'},
        '08:40 West directly precedes the first North event at 09:00.')
    docs={'register.md':'Certificate K-204 has serial ZX-7319; issued to Aster Instruments.'}
    for i in range(180):
        docs[f'archives/box_{i%9}/record_{i:03}.md']=(f'Certificate K-{300+i}: serial ZX-{9000+i}; issuer Aster Archives. '
                                                   'This archive catalogs calibration equipment and historical renewals.')
    # Deliberately no special filename for the answer and no target repeated in every distractor.
    docs['archives/box_7/record_193.md']=docs.pop('register.md')
    put('large_corpus_exact','Точный идентификатор среди большого числа файлов','hard',
        'Using kb/, find the serial number of certificate K-204 issued to Aster Instruments. Return only the serial.',
        'ZX-7319',docs,'archives/box_7/record_193.md is the exact certificate; other certificate IDs differ.')
    put('table_lookup','Ячейка markdown-таблицы','easy',
        'Using kb/, return the recovery code for environment staging and service mail. Return only the code.',
        'R-72',{'operations.md':'| Environment | Service | Recovery code |\n|---|---|---|\n'
              '| production | mail | R-27 |\n| staging | web | R-17 |\n| staging | mail | R-72 |'},
        'Both row keys are needed; staging/mail selects R-72.')
    put('negated_relation','Отказ, перенос и окончательное место','hard',
        'Using kb/, in which city was the 2025 Orion workshop actually held? Return only the city.', 'Brno',
        {'proposal.md':'The 2025 Orion workshop was proposed for Vienna; the venue did not accept.',
         'schedule.md':'A provisional schedule listed Graz, later cancelled.',
         'minutes.md':'The completed 2025 Orion workshop took place in Brno on June 12. Vienna and Graz were not used.',
         'previous.md':'The 2024 Orion workshop was held in Vienna.'},
        'Completed event in minutes.md, rather than proposals or previous year.')
    put('cross_document_count','Подсчёт уникальных сущностей по источникам','hard',
        'Using kb/, how many distinct researchers have an approved safety certificate AND an active lab membership? '
        'Person IDs identify researchers; duplicate mentions count once. Return only an integer.',2,
        {'certificates.md':'R1 approved. R2 pending. R3 approved. R4 approved. R1 approved.',
         'memberships.md':'R1 active. R2 active. R3 inactive. R4 active. R5 active.'},
        'Intersection is {R1,R4}; duplicates and pending/inactive records excluded.')
    put('structured_and_prose','Связь между JSON и текстовым документом','hard',
        'Using kb/, what is the full name of the custodian of the asset whose public label is Blue Lantern? '
        'Return only the full name.', 'Ada Finch',
        {'assets.json':json.dumps({'assets':[{'label':'Blue Lantern','custodian':'E8'},{'label':'Blue Lamp','custodian':'E9'}]}),
         'staff/roster.txt':'E8 = Ada Finch\nE9 = Ada French\nE18 = Ida Finch'},
        'Join Blue Lantern custodian E8 from JSON to the roster text.')
    put('conflicting_equal_sources','Два равноправных противоречащих источника','medium',
        'Using only kb/, what is the exact opening year of the Vale archive? Return only the year.', 'IMPOSSIBLE',
        {'source_a.md':'Vale archive opened in 1921. This is an unsigned undated copy.',
         'source_b.md':'Vale archive opened in 1924. This is an unsigned undated copy.'},
        'No precedence or corroboration distinguishes conflicting equal-status copies.',solvable=False)
    put('absent_relation','Отсутствующая связь при похожих данных','medium',
        'Using only kb/, where was botanist Lena Rook born? Return only the city.', 'IMPOSSIBLE',
        {'people.md':'Lena Rook is a botanist employed in Bern. Leon Rook is a physicist born in Oslo.',
         'projects.md':'Lena Rook led a field expedition to Quito in 2018.'},
        'Employment and travel locations do not determine Lena birth city; Leon is another person.',solvable=False)


def test_script(checks):
    return ('import unittest\nimport solution as m\n\nclass Cases(unittest.TestCase):\n'
            + ''.join(f'    def test_{i:03}(self):\n'+textwrap.indent(textwrap.dedent(body).strip(),'        ')+'\n\n'
                      for i,body in enumerate(checks))
            + "if __name__ == '__main__':\n    unittest.main()\n")


def code_task(family,title,level,contract,buggy,reference,public,private):
    add('coding',family,title,level,
        'Fix solution.py. '+contract+' Keep the implementation in solution.py and use only the Python standard library. '
        'Run `python3 test_solution.py` to check the examples. '
        'Do not edit the tests. The implementation must satisfy the specification for other inputs too. '
        'After fixing the implementation, the final answer is DONE.', 'tests_pass',
        {'solution.py':textwrap.dedent(buggy).lstrip(),'test_solution.py':test_script(public)},
        why='Reference implementation passes public and private tests; supplied implementation must fail public tests.',
        check='unittest',reference=textwrap.dedent(reference).lstrip(),private=test_script(private))


def coding():
    code_task('stable_unique','Устранение дублей с сохранением порядка','easy',
        'unique(values) accepts a list of hashable values and returns a new list containing the first '
        'occurrence of each distinct value, in original order. Do not change the input.',
        'def unique(values):\n    return sorted(set(values))\n',
        'def unique(values):\n    return list(dict.fromkeys(values))\n',
        ["self.assertEqual(m.unique([3,1,3,2]), [3,1,2])"],
        ["self.assertEqual(m.unique([]), [])", "self.assertEqual(m.unique(['z','a','z','b']), ['z','a','b'])",
         "v=[None,3,'a',None,3]; before=v[:]; self.assertEqual(m.unique(v),[None,3,'a']); self.assertEqual(v,before)",
         "import random\nr=random.Random(11)\nfor _ in range(80):\n v=[r.randrange(9) for _ in range(r.randrange(50))]\n want=[]\n for x in v:\n  if x not in want: want.append(x)\n self.assertEqual(m.unique(v),want)"])
    code_task('run_length','Декодирование пар и нулевые повторы','easy',
        'expand(pairs) takes a list of (text,count) pairs. Each text is a string, count must be an ordinary '
        'nonnegative int (bool is invalid). Return concatenation of text repeated count times in pair order. '
        'Raise ValueError for invalid counts; empty input returns an empty string.',
        'def expand(pairs):\n    return "".join(text for text, count in pairs)\n',
        '''def expand(pairs):
    parts=[]
    for text,count in pairs:
        if type(count) is not int or count<0: raise ValueError('count')
        parts.append(text*count)
    return ''.join(parts)
''', ["self.assertEqual(m.expand([('ab',2),('x',0)]),'abab')"],
        ["self.assertEqual(m.expand([]),'')", "self.assertEqual(m.expand([('',9),('x',3),('yz',1)]),'xxxyz')",
         "for n in [-1,True,1.5,'2']:\n with self.assertRaises(ValueError): m.expand([('x',n)])"])
    code_task('half_open_union','Объединение интервалов и длина покрытия','medium',
        'covered(intervals) accepts pairs (start,end) of integers with start<=end. Return total length '
        'covered by their half-open union. Ignore zero-length intervals, support negatives and unsorted '
        'input, and do not mutate the input.',
        'def covered(intervals):\n    return sum(b-a for a,b in intervals)\n',
        '''def covered(intervals):
    end=None; total=0
    for a,b in sorted(intervals):
        total+=max(0,b-max(a,end if end is not None else a))
        end=b if end is None else max(end,b)
    return total
''',["self.assertEqual(m.covered([(1,4),(3,6)]),5)"],
        ["self.assertEqual(m.covered([]),0)", "v=[(3,3),(-5,2),(0,1),(2,6)]; before=v[:]; self.assertEqual(m.covered(v),11); self.assertEqual(v,before)",
         "import random\nr=random.Random(12)\nfor _ in range(100):\n v=[tuple(sorted([r.randrange(-15,16),r.randrange(-15,16)])) for _ in range(r.randrange(12))]\n cells=set()\n for a,b in v: cells.update(range(a,b))\n self.assertEqual(m.covered(v),len(cells))"])
    code_task('csv_reader','Разбор CSV с кавычками и переносами','medium',
        'read_rows(text) parses comma-delimited CSV with standard double-quote escaping. Return a list '
        'of lists of strings, including the header as an ordinary row. Preserve spaces and quoted '
        'embedded newlines. Empty text yields an empty list.',
        'def read_rows(text):\n    return [line.split(",") for line in text.splitlines()]\n',
        'import csv, io\ndef read_rows(text):\n    return list(csv.reader(io.StringIO(text, newline="")))\n',
        ["self.assertEqual(m.read_rows('a,b\\n1,\"x,y\"\\n'),[['a','b'],['1','x,y']])"],
        ["self.assertEqual(m.read_rows(''),[])", "self.assertEqual(m.read_rows('\"a\\nb\",\"say \"\"hi\"\"\"\\n'),[['a\\nb','say \"hi\"']])",
         "import csv,io,random\nr=random.Random(13)\nfor _ in range(60):\n rows=[[r.choice(['a,b','x\\ny','\"','', ' spaced ']) for _ in range(3)] for _ in range(5)]\n s=io.StringIO(newline=''); csv.writer(s,lineterminator='\\n').writerows(rows)\n self.assertEqual(m.read_rows(s.getvalue()), rows)"])
    code_task('lower_bound','Левая граница в отсортированном массиве','easy',
        'lower_bound(values,target) returns the first index i with values[i]>=target, or len(values) '
        'if there is no such index. values is a sorted list of integers, possibly empty or containing '
        'duplicates. Do not mutate values.',
        'def lower_bound(values,target):\n    return values.index(target) if target in values else -1\n',
        '''def lower_bound(values,target):
    lo,hi=0,len(values)
    while lo<hi:
        mid=(lo+hi)//2
        if values[mid]<target: lo=mid+1
        else: hi=mid
    return lo
''',["self.assertEqual(m.lower_bound([1,3,3,8],4),3)"],
        ["self.assertEqual(m.lower_bound([],7),0)",
         "import random,bisect\nr=random.Random(14)\nfor _ in range(120):\n v=sorted(r.randrange(-20,21) for _ in range(r.randrange(60))); t=r.randrange(-25,26); before=v[:]\n self.assertEqual(m.lower_bound(v,t),bisect.bisect_left(v,t)); self.assertEqual(v,before)"])
    code_task('nested_paths','Обход вложенных словарей и списков','medium',
        'lookup(data,path,default=None) follows a sequence of keys: dictionaries use matching keys, '
        'lists use nonnegative ordinary integer indices (bool is invalid). Missing keys, out-of-range '
        'indices or incompatible node types return default. An empty path returns data. A stored None '
        'is a real value, not a missing value.',
        'def lookup(data,path,default=None):\n    for key in path: data=data.get(key,default)\n    return data\n',
        '''def lookup(data,path,default=None):
    for key in path:
        if isinstance(data,dict):
            try: data=data[key]
            except (KeyError,TypeError): return default
        elif isinstance(data,list) and type(key) is int and 0<=key<len(data): data=data[key]
        else: return default
    return data
''',["self.assertEqual(m.lookup({'a':[{'b':7}]},['a',0,'b']),7)"],
        ["self.assertIsNone(m.lookup({'a':None},['a'],99))", "self.assertEqual(m.lookup({'a':[1]},['a',-1],99),99)",
         "for path in [['a',True],['a',2],['a','0'],['x'],['a',0,'b']]:\n self.assertEqual(m.lookup({'a':[1]},path,'missing'),'missing')",
         "d={'a':1}; self.assertIs(m.lookup(d,[]),d)"])
    code_task('dependency_order','Топологический порядок с выбором при равенстве','hard',
        'order(deps) takes a dict from string node names to lists of prerequisite node names. '
        'Nodes mentioned only as prerequisites also count. Return a topological ordering, always '
        'choosing the lexicographically smallest currently available node. Duplicate prerequisites '
        'count once. Raise ValueError for any cycle. Do not mutate deps.',
        'def order(deps):\n    return sorted(deps)\n',
        '''import heapq
def order(deps):
    nodes=set(deps)|{x for vs in deps.values() for x in vs}
    incoming={n:set(deps.get(n,[])) for n in nodes}
    ready=[n for n in nodes if not incoming[n]]; heapq.heapify(ready)
    out=[]
    while ready:
        n=heapq.heappop(ready); out.append(n)
        for v in nodes:
            if n in incoming[v]:
                incoming[v].remove(n)
                if not incoming[v]: heapq.heappush(ready,v)
    if len(out)!=len(nodes): raise ValueError('cycle')
    return out
''',["self.assertEqual(m.order({'a':['z'],'z':[]}),['z','a'])"],
        ["self.assertEqual(m.order({}),[])", "self.assertEqual(m.order({'b':['a','a'],'d':['c']}),['a','b','c','d'])",
         "for d in [{'a':['a']},{'a':['b'],'b':['a']},{'z':[],'x':['y'],'y':['x']}]:\n with self.assertRaises(ValueError): m.order(d)",
         "import random,copy,itertools\nr=random.Random(15)\nfor _ in range(25):\n names=list('abcde'); r.shuffle(names)\n d={n:[p for p in names[:i] if r.random()<0.4] for i,n in enumerate(names)}\n original=copy.deepcopy(d)\n valid=[p for p in itertools.permutations(sorted(names)) if all(p.index(u)<p.index(v) for v,us in d.items() for u in us)]\n self.assertEqual(m.order(d),list(min(valid))); self.assertEqual(d,original)"])
    code_task('ttl_store','Хранилище со сроком действия','hard',
        'Store() supports put(key,value,now,ttl) and get(key,now). Times are integer ticks and callers '
        'use nondecreasing now. put replaces any previous value and expires at now+ttl; at that exact '
        'time it is already absent. A nonpositive ttl removes the key immediately. get returns None '
        'when absent or expired. Keys are strings. Values can be any object.',
        '''class Store:
    def __init__(self): self.data={}
    def put(self,key,value,now,ttl): self.data[key]=value
    def get(self,key,now): return self.data.get(key)
''',
        '''class Store:
    def __init__(self): self.data={}
    def put(self,key,value,now,ttl):
        if ttl<=0: self.data.pop(key,None)
        else: self.data[key]=(value,now+ttl)
    def get(self,key,now):
        if key not in self.data: return None
        value,end=self.data[key]
        if now>=end:
            del self.data[key]; return None
        return value
''',["s=m.Store(); s.put('a',7,0,3); self.assertIsNone(s.get('a',3))"],
        ["s=m.Store(); self.assertIsNone(s.get('missing',0)); s.put('a',1,0,5); s.put('a',2,1,1); self.assertEqual(s.get('a',1),2); self.assertIsNone(s.get('a',2))",
         "s=m.Store(); s.put('a',8,0,10); s.put('a',7,1,0); self.assertIsNone(s.get('a',1))",
         "import random\nr=random.Random(16); s=m.Store(); history=[]\nfor t in range(140):\n key=r.choice('abcd')\n if r.random()<.6:\n  value=r.randrange(99); ttl=r.randrange(-1,9); s.put(key,value,t,ttl); history.append((key,value,t,ttl))\n else:\n  old=next((h for h in reversed(history) if h[0]==key),None)\n  want=old[1] if old and t<old[2]+old[3] else None\n  self.assertEqual(s.get(key,t),want)"])
    code_task('rational_decimal','Денежное округление без двоичной ошибки','medium',
        'to_cents(text) takes a valid finite decimal string with optional sign and decimal point '
        '(no exponent, at most 20 digits). Return integer cents rounded to nearest, with ties away from zero.',
        'def to_cents(text):\n    return round(float(text)*100)\n',
        'from decimal import Decimal, ROUND_HALF_UP\ndef to_cents(text):\n    return int((Decimal(text)*100).quantize(Decimal(1),rounding=ROUND_HALF_UP))\n',
        ["self.assertEqual(m.to_cents('1.005'),101)"],
        ["self.assertEqual(m.to_cents('-1.005'),-101)", "self.assertEqual(m.to_cents('0.0049'),0)",
         "from fractions import Fraction\nimport random\nr=random.Random(17)\nfor _ in range(100):\n n=r.randrange(-999999,999999); text=f'{n/1000:.3f}'; v=Fraction(text)*100\n sign=1 if v>=0 else -1; v=abs(v); want=sign*((2*v.numerator+v.denominator)//(2*v.denominator))\n self.assertEqual(m.to_cents(text),want)",
         "self.assertEqual(m.to_cents('123456789012345.995'),12345678901234600)"])
    code_task('shortest_path','Кратчайшие пути с нулевыми рёбрами','hard',
        'distances(edges,start) accepts a list of directed (source,target,weight) edges, string nodes, '
        'and nonnegative integer weights. Return a dict of shortest distances for exactly the nodes '
        'reachable from start, including start at zero. Parallel edges and zero-cost cycles are allowed.',
        '''def distances(edges,start):
    result={start:0}
    for a,b,w in edges:
        if a in result: result[b]=result[a]+w
    return result
''',
        '''import heapq
def distances(edges,start):
    graph={}
    for a,b,w in edges: graph.setdefault(a,[]).append((b,w))
    ds={start:0}; q=[(0,start)]
    while q:
        d,u=heapq.heappop(q)
        if d!=ds[u]: continue
        for v,w in graph.get(u,[]):
            if d+w<ds.get(v,float('inf')):
                ds[v]=d+w; heapq.heappush(q,(d+w,v))
    return ds
''',["self.assertEqual(m.distances([('b','c',1),('a','b',2)],'a'),{'a':0,'b':2,'c':3})"],
        ["self.assertEqual(m.distances([],'x'),{'x':0})",
         "self.assertEqual(m.distances([('a','b',0),('b','a',0),('a','b',9),('x','y',1)],'a'),{'a':0,'b':0})",
         "import random\nr=random.Random(18)\nfor _ in range(60):\n es=[(a,b,r.randrange(8)) for a in 'abcde' for b in 'abcde' if r.random()<.25]; r.shuffle(es)\n ds={'a':0}\n for k in range(5):\n  for a,b,w in es:\n   if a in ds: ds[b]=min(ds.get(b,float('inf')),ds[a]+w)\n self.assertEqual(m.distances(es,'a'),ds)"])
    code_task('transpose_ragged','Транспонирование неровных строк','easy',
        'transpose(rows,fill=None) takes a list of lists and returns columns as lists. Output width '
        'equals the longest input row length; missing cells use fill. Empty input or all empty rows '
        'returns an empty list. Do not change input rows.',
        'def transpose(rows,fill=None):\n    return [list(x) for x in zip(*rows)]\n',
        '''def transpose(rows,fill=None):
    return [[row[i] if i<len(row) else fill for row in rows] for i in range(max(map(len,rows),default=0))]
''',["self.assertEqual(m.transpose([[1,2],[3]],0),[[1,3],[2,0]])"],
        ["self.assertEqual(m.transpose([]),[]); self.assertEqual(m.transpose([[],[]]),[])",
         "r=[[],[None,4],[5]]; self.assertEqual(m.transpose(r,'x'),[['x',None,5],['x',4,'x']]); self.assertEqual(r,[[],[None,4],[5]])"])
    code_task('expression_parser','Парсер вложенных арифметических выражений','hard',
        'calculate(text) evaluates decimal integer literals, +, -, *, parentheses, repeated unary +/- '
        'and surrounding/inter-token whitespace with normal arithmetic precedence. Return an ordinary int. '
        'Reject all other syntax (names, calls, booleans, division, powers, lists and non-decimal literals) '
        'with ValueError. Do not use eval or exec.',
        'def calculate(text):\n    return sum(int(t) for t in text.split("+"))\n',
        '''import ast,re
def calculate(text):
    if not isinstance(text,str) or re.search(r'[^0-9+*()\\s-]',text): raise ValueError('syntax')
    normalized=re.sub(r'\\s+',' ',text).strip()
    normalized=re.sub(r'\\d+',lambda m:str(int(m.group())),normalized)
    try: node=ast.parse(normalized,mode='eval').body
    except (SyntaxError,ValueError): raise ValueError('syntax')
    def visit(n):
        if isinstance(n,ast.Constant) and type(n.value) is int: return n.value
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
            v=visit(n.operand); return v if isinstance(n.op,ast.UAdd) else -v
        if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub,ast.Mult)):
            a,b=visit(n.left),visit(n.right)
            return a+b if isinstance(n.op,ast.Add) else a-b if isinstance(n.op,ast.Sub) else a*b
        raise ValueError('syntax')
    return visit(node)
''',["self.assertEqual(m.calculate('2*(3+4)-5'),9)"],
        ["self.assertEqual(m.calculate('  --3 + -2*4  '),-5)",
         "self.assertEqual(m.calculate('001 +\\n 002'),3)",
         "for s in ['True','x','f()','1/2','2**3','[2]','0x10','', '1+','1.5','1//2']:\n with self.assertRaises(ValueError): m.calculate(s)",
         "import random\nr=random.Random(19)\ndef tree(d):\n if d==0:\n  n=r.randrange(10); return str(n),n\n a,x=tree(d-1); b,y=tree(d-1); op=r.choice(['+','-','*'])\n return '('+a+op+b+')',x+y if op=='+' else x-y if op=='-' else x*y\nfor _ in range(70):\n s,want=tree(3); self.assertEqual(m.calculate(s),want)"])
    code_task('escaped_split','Разделители и экранирование','medium',
        r"split_fields(text) splits on unescaped |. A backslash escapes the next character, whether it is |, "
        r"a backslash or any other character. Remove the escaping backslash. Preserve empty fields, including "
        r"trailing ones. A final unmatched backslash is a literal backslash. Empty text produces [''].",
        'def split_fields(text):\n    return text.split("|")\n',
        '''def split_fields(text):
    out=[]; part=[]; escaped=False
    for c in text:
        if escaped: part.append(c); escaped=False
        elif c=='\\\\': escaped=True
        elif c=='|': out.append(''.join(part)); part=[]
        else: part.append(c)
    if escaped: part.append('\\\\')
    out.append(''.join(part)); return out
''',["self.assertEqual(m.split_fields(r'a\|b|c'),['a|b','c'])"],
        ["self.assertEqual(m.split_fields(''),['']); self.assertEqual(m.split_fields('||'),['','',''])",
         "self.assertEqual(m.split_fields('abc'+chr(92)),['abc'+chr(92)])",
         "self.assertEqual(m.split_fields(chr(92)+chr(92)+'|z'),[chr(92),'z'])",
         "import random\nr=random.Random(20)\nfor _ in range(70):\n fields=[''.join(r.choice('ab|'+chr(92)) for _ in range(r.randrange(8))) for _ in range(4)]\n encoded='|'.join(''.join(chr(92)+c if c in '|'+chr(92) else c for c in s) for s in fields)\n self.assertEqual(m.split_fields(encoded),fields)"])
    code_task('edit_distance','Редакционное расстояние','hard',
        'distance(a,b) returns the minimum number of single-character insertions, deletions and '
        'substitutions to turn string a into b, each cost 1. Support empty strings and arbitrary Unicode '
        'code points. A transposition is not a special operation.',
        'def distance(a,b):\n    return abs(len(a)-len(b))+sum(x!=y for x,y in zip(a,b))\n',
        '''def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        new=[i]
        for j,y in enumerate(b,1): new.append(min(new[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=new
    return row[-1]
''',["self.assertEqual(m.distance('abc','zabc'),1)"],
        ["self.assertEqual(m.distance('','abc'),3); self.assertEqual(m.distance('ab','ba'),2)",
         "self.assertEqual(m.distance('café','cafe'),1)",
         "from functools import lru_cache\nimport random\nr=random.Random(21)\n@lru_cache(None)\ndef oracle(a,b):\n if not a: return len(b)\n if not b: return len(a)\n return min(1+oracle(a[1:],b),1+oracle(a,b[1:]),(a[0]!=b[0])+oracle(a[1:],b[1:]))\nfor _ in range(80):\n a=''.join(r.choice('abc') for _ in range(r.randrange(7))); b=''.join(r.choice('abc') for _ in range(r.randrange(7)))\n self.assertEqual(m.distance(a,b),oracle(a,b))"])
    code_task('transaction_rollback','Атомарный пакет операций','hard',
        'apply(balances,transfers) returns a new balance dict after processing (sender,recipient,amount) '
        'transfers in order. Both accounts must exist. Amount must be an ordinary nonnegative int '
        '(not bool), and the sender must currently have enough funds. Any invalid transfer raises '
        'ValueError. Never mutate the original balances, including on failure. A self-transfer '
        'still requires enough funds and has no net effect.',
        '''def apply(balances,transfers):
    for a,b,n in transfers:
        balances[a]-=n; balances[b]+=n
    return balances
''',
        '''def apply(balances,transfers):
    result=dict(balances)
    for a,b,n in transfers:
        if a not in result or b not in result or type(n) is not int or n<0 or result[a]<n: raise ValueError('transfer')
        result[a]-=n; result[b]+=n
    return result
''',["d={'a':5,'b':0}; self.assertEqual(m.apply(d,[('a','b',3)]),{'a':2,'b':3}); self.assertEqual(d,{'a':5,'b':0})"],
        ["d={'a':5,'b':0}\nwith self.assertRaises(ValueError): m.apply(d,[('a','b',3),('b','a',4)])\nself.assertEqual(d,{'a':5,'b':0})",
         "for t in [('a','b',True),('a','b',-1),('a','x',0),('x','b',0),('a','a',6),('a','b',1.5)]:\n with self.assertRaises(ValueError): m.apply({'a':5,'b':0},[t])",
         "d={'a':5,'b':0}; result=m.apply(d,[('a','a',5),('a','b',0)]); self.assertEqual(result,d); self.assertIsNot(result,d)"])
    code_task('version_compare','Сравнение числовых версий','medium',
        'compare(a,b) accepts nonempty version strings of dot-separated nonnegative integer components. '
        'Components may have leading zeros. Compare numerically, treating missing trailing components as '
        'zero. Return exactly -1, 0 or 1. Inputs are valid; no prerelease suffixes are used.',
        'def compare(a,b):\n    return (a>b)-(a<b)\n',
        '''def compare(a,b):
    x=list(map(int,a.split('.'))); y=list(map(int,b.split('.')))
    size=max(len(x),len(y)); x+=[0]*(size-len(x)); y+=[0]*(size-len(y))
    return (x>y)-(x<y)
''',["self.assertEqual(m.compare('1.10','1.9'),1)"],
        ["self.assertEqual(m.compare('1','01.0.00'),0); self.assertEqual(m.compare('0.1','1'),-1)",
         "import random\nr=random.Random(22)\nfor _ in range(100):\n x=[r.randrange(20) for _ in range(r.randrange(1,6))]; y=[r.randrange(20) for _ in range(r.randrange(1,6))]\n xp=x+[0]*(5-len(x)); yp=y+[0]*(5-len(y)); want=(xp>yp)-(xp<yp)\n self.assertEqual(m.compare('.'.join(map(str,x)),'.'.join(map(str,y))),want)"])


def artifacts():
    CASES.clear()
    maths(); data_tasks(); searches(); coding()
    assert len(CASES)==64 and len({c['family'] for c in CASES})==64
    artifacts={}; manifest=[]; counters=Counter()
    holdout_indices={2,5,8,11,13,15}
    smoke_indices={0,7,12}
    # Mix task types in IDs without encoding difficulty, split or answerability.
    ordered=[]
    for i in range(16):
        group=[CASES[k*16+i] for k in range(4)]
        random.Random(SEED+i).shuffle(group)
        ordered.extend(group)
    for index,case in enumerate(ordered,1):
        task_id=f'd{index:03}'
        n=counters[case['type']]; counters[case['type']]+=1
        split='holdout' if n in holdout_indices else 'dev'
        reward=[3,1,5,2,4,2,5,1,3,4,2,3,1,5,4,2][n]
        instruction=case['prompt']+TAIL
        task=dict(task_id=task_id,task_type=case['type'],instruction=instruction,reward=reward,check=case['check'])
        base=f'input/{task_id}/'
        artifacts[base+'task.json']=js(task)
        for path,content in case['files'].items(): artifacts[base+path]=content
        ref=dict(expected=case['expected'],solvable=case['solvable'],explanation=case['why'])
        artifacts[f'references/{task_id}/answer.json']=js(ref)
        if case['reference'] is not None:
            artifacts[f'references/{task_id}/solution.py']=case['reference']
            artifacts[f'references/{task_id}/test_private.py']=case['private']
        manifest.append(dict(id=task_id,type=case['type'],family=case['family'],title=case['title'],
                             difficulty=case['difficulty'],split=split,smoke=n in smoke_indices,
                             reward=reward,check=case['check'],solvable=case['solvable']))
    def digest(prefix):
        h=hashlib.sha256()
        for name,content in sorted(artifacts.items()):
            if name.startswith(prefix):
                payload=content.encode('utf-8')
                h.update(name.encode('utf-8')+b'\0'+str(len(payload)).encode()+b'\0'+payload)
        return h.hexdigest()
    metadata=dict(version='diverse-v1',seed=SEED,input_sha256=digest('input/'),
                  references_sha256=digest('references/'),tasks=manifest)
    artifacts['manifest.json']=js(metadata)
    catalog=['# Каталог diverse-v1','',
             'Сложность — предварительная экспертная оценка, а не измеренная вероятность решения.',
             'Контрольные задачи (`holdout`) не используем при подборе промптов и лимитов.', '',
             '| ID | Тип | Задача | Сложность | Выборка | Быстрая |',
             '|---|---|---|---|---|---|']
    for c in manifest:
        catalog.append(f"| [{c['id']}](input/{c['id']}/task.json) | {c['type']} | {c['title']} | {c['difficulty']} | {c['split']} | {'да' if c['smoke'] else ''} |")
    artifacts['CATALOG.md']='\n'.join(catalog)+'\n'
    return artifacts


if __name__=='__main__':
    for name,content in artifacts().items():
        path=ROOT/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(content.encode('utf-8'))
    print('Generated diverse-v1: 64 distinct tasks, 40 dev, 24 holdout, 12 smoke (subset of dev).')
