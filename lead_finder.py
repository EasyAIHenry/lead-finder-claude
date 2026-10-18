"""Lead finder: who to reach out to first, and a message for each one.

1. signals  Companies hiring right now for the kind of work you sell.
            Singapore: the public MyCareersFuture job board (free, no key).
            Any country: homepage URLs you list in extra_sites.txt.
2. scrape   ScrapeGraphAI reads each company's homepage with a free local model (Ollama).
3. score    Plain rules from config.yaml, so the ranking is the same every run.
4. top 10   Why each one, which offer fits, how to reach them, an opener
            and a tracked link to your enquiry form.

Run:   python lead_finder.py                 (full run, max_companies from config.yaml)
       python lead_finder.py --max 3         (quick test, 3 companies)
       python lead_finder.py --config my.yaml --fresh
Model: LEAD_MODEL=ollama/llama3.2 python lead_finder.py   (default ollama/qwen2.5:7b-instruct)

It never sends anything. You read the list and send each message yourself.
"""
import argparse, csv, json, os, re, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.environ.get("LEAD_MODEL", "ollama/qwen2.5:7b-instruct")
JOB_BOARD = "https://api.mycareersfuture.gov.sg/v2/jobs?"
# Links that point at a job site, not the company's own homepage.
JOB_HOSTS = ("myworkdayjobs", "workday", "greenhouse", "lever.co", "linkedin", "facebook", "instagram",
             "jobstreet", "mycareersfuture", "indeed", "glassdoor", "careers.")

PROMPT = (
    "From this company website extract: company_name, what_they_do (max 12 words), industry, "
    "sells_to (consumers, businesses, or both), countries_or_regions (list where they operate or have offices), "
    "posts_content (true if the site shows videos, a blog, campaigns or social media links), "
    "public_contact_email, contact_page_url, linkedin_url. "
    "Only use information visible on the site. Use null for anything missing. Return JSON."
)


# ---------- config ----------

def load_config(path):
    try:
        import yaml
    except ImportError:
        sys.exit("pyyaml is missing. Run: pip install -r requirements.txt")
    if not os.path.exists(path):
        sys.exit(f"No config at {path}. Copy config.example.yaml to config.yaml and fill it in "
                 "(or ask Claude to do it for you).")
    cfg = yaml.safe_load(open(path)) or {}
    for key in ("business", "routes"):
        if key not in cfg:
            sys.exit(f"config is missing the '{key}' section. Compare it with config.example.yaml.")
    link = cfg["business"].get("enquiry_link", "")
    if "{src}" not in link:
        sys.exit("business.enquiry_link needs {src} in it, for example https://yoursite.com/contact?src={src}")
    for name, r in cfg["routes"].items():
        r["_title"] = re.compile(r["title_regex"], re.I)
        r["_ignore"] = re.compile(r["ignore_titles_regex"], re.I) if r.get("ignore_titles_regex") else None
        r.setdefault("label", name)
        r.setdefault("bonus", 0)
        r.setdefault("searches", [])
    cfg["_competitor"] = re.compile("|".join(cfg.get("competitor_words", [])) or r"$^", re.I)
    ih = cfg.get("in_house_titles_regex")
    cfg["_in_house"] = re.compile(ih, re.I) if ih else None
    cfg.setdefault("in_house_points", -3)
    cfg.setdefault("skip_words", [])
    cfg.setdefault("good_industries", [])
    cfg.setdefault("size", {"big": 200, "mid": 50, "small": 20})
    cfg.setdefault("max_companies", 40)
    cfg.setdefault("per_search", 100)
    return cfg


# ---------- 1. signals ----------

def home(url):
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    u = urllib.parse.urlparse(url)
    if not u.netloc or any(h in u.netloc for h in JOB_HOSTS):
        return ""
    return f"{u.scheme}://{u.netloc}/"


def get_json(url):
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def skipped(name, cfg):
    padded = f" {name.lower()} "
    return any(w.lower() in padded for w in cfg["skip_words"])


def job_board_signals(cfg):
    """Singapore companies hiring right now for roles that match a route."""
    cos = {}
    for route_name, route in cfg["routes"].items():
        for q in route["searches"]:
            url = JOB_BOARD + urllib.parse.urlencode(
                {"search": q, "limit": cfg["per_search"], "page": 0, "sortBy": "new_posting_date"})
            try:
                jobs = get_json(url).get("results", [])
            except Exception as e:
                print(f"   search failed: {q} ({str(e)[:60]})")
                continue
            for j in jobs:
                c = j.get("hiringCompany") or j.get("postedCompany") or {}
                name = (c.get("name") or "").strip()
                if not name or skipped(name, cfg):
                    continue
                title = (j.get("title") or "").strip()
                # The job board's search is loose, so a job only counts if its title really matches a route.
                hits = [rn for rn, r in cfg["routes"].items()
                        if r["_title"].search(title) and not (r["_ignore"] and r["_ignore"].search(title))]
                if not hits:
                    continue
                site = home((c.get("companyUrl") or "").strip())
                key = c.get("uen") or name
                row = cos.setdefault(key, {"company": name, "website": site, "employees": c.get("employeeCount"),
                                           "roles": [], "routes": set(), "job_link": "", "posted": "",
                                           "source": "job board"})
                posted = (j.get("metadata") or {}).get("newPostingDate") or ""
                if posted > row["posted"]:
                    row["posted"] = posted
                if site and not row["website"]:
                    row["website"] = site
                if not row["job_link"]:
                    row["job_link"] = (j.get("metadata") or {}).get("jobDetailsUrl", "")
                if title not in row["roles"]:
                    row["roles"].append(title)
                row["routes"].update(hits)
            time.sleep(0.5)
    out = []
    for r in cos.values():
        if r["website"]:
            r["routes"] = [rn for rn in cfg["routes"] if rn in r["routes"]]   # keep config order
            out.append(r)
    return out


def extra_signals(cfg):
    """Homepages you picked by hand, one per line in extra_sites.txt. Works for any country."""
    path = os.path.join(HERE, cfg.get("extra_sites_file", "extra_sites.txt"))
    if not os.path.exists(path):
        return []
    default_route = cfg.get("default_route") or next(iter(cfg["routes"]))
    out = []
    for line in open(path):
        u = line.strip()
        if not u or u.startswith("#"):
            continue
        site = home(u) or (u if u.startswith("http") else "https://" + u)
        out.append({"company": urllib.parse.urlparse(site).netloc.replace("www.", ""), "website": site,
                    "employees": None, "roles": [], "routes": [default_route], "job_link": "", "posted": "",
                    "source": "your list"})
    return out


# ---------- 2. scrape ----------

def scrape(url, cache, cache_path):
    from scrapegraphai.graphs import SmartScraperGraph
    if url in cache:
        return cache[url]
    config = {"llm": {"model": MODEL, "model_tokens": 8192, "format": "json"}, "headless": True, "verbose": False}
    r = SmartScraperGraph(prompt=PROMPT, source=url, config=config).run()
    if isinstance(r, dict) and isinstance(r.get("content"), dict):
        r = r["content"]
    r = r if isinstance(r, dict) else {}
    cache[url] = r
    json.dump(cache, open(cache_path, "w"), indent=1)
    return r


# ---------- 3. score ----------

def blank(v):
    return v in (None, "", "null", "NA", "N/A", "None", "available", [], {})


def contact(c):
    s = c.get("site", {})
    em = s.get("public_contact_email")
    em = em if isinstance(em, str) and "@" in em else ""
    pg = s.get("contact_page_url")
    pg = urllib.parse.urljoin(c["website"], pg) if isinstance(pg, str) and not blank(pg) else ""
    li = s.get("linkedin_url")
    li = li if isinstance(li, str) and "linkedin.com" in li else ""
    return em, pg, li


def score(c, cfg):
    pts, why = 0, []
    s = c.get("site", {})
    blurb = f"{s.get('what_they_do') or ''} {s.get('industry') or ''}"
    if cfg["_competitor"].search(blurb) or cfg["_competitor"].search(c["company"]):
        return -10, [f"looks like a competitor or a middleman ({s.get('what_they_do') or c['company']})"]
    n = len(c["roles"])
    if n:
        pts += min(n, 3) * 3
        why.append(f"hiring {n} matching role{'s' if n > 1 else ''}: {', '.join(c['roles'][:3])}")
    else:
        pts += 3
        why.append("on your own list")
    in_house = [t for t in c["roles"] if cfg["_in_house"] and cfg["_in_house"].search(t)]
    if in_house:
        pts += cfg["in_house_points"]
        why.append(f"hiring the work you sell in-house ({in_house[0]}): pitch help around that hire, or skip")
    for rn in (c["routes"] if c["roles"] else []):   # bonus only for real job-ad matches
        r = cfg["routes"][rn]
        if r["bonus"]:
            pts += r["bonus"]
            why.append(r.get("bonus_reason") or f"fits {r['label']}")
    e = c.get("employees") or 0
    sz = cfg["size"]
    if e >= sz["big"]:
        pts += 4; why.append(f"{e} staff")
    elif e >= sz["mid"]:
        pts += 2; why.append(f"{e} staff")
    elif e and e < sz["small"]:
        pts -= 2; why.append(f"only {e} staff")
    regions = s.get("countries_or_regions")
    if isinstance(regions, list) and len([x for x in regions if x]) > 1:
        pts += 2; why.append("works across " + ", ".join(map(str, regions[:4])))
    ind = str(s.get("industry") or "").lower()
    if ind and any(k.lower() in ind for k in cfg["good_industries"]):
        pts += 2; why.append(f"industry: {s.get('industry')}")
    if s.get("posts_content") in (True, "true", "True"):
        pts += 1; why.append("already publishes content")
    if not s or all(blank(v) for v in s.values()):
        pts -= 3; why.append("website couldn't be read, check it by hand")
    if any(contact(c)):
        pts += 1
    return pts, why


# ---------- 4. opener ----------

SMALL_WORDS = {"THE", "AND", "OF", "FOR", "AT", "IN", "ON", "TO"}


def smart_case(text):
    """SOCIAL MEDIA EXECUTIVE -> Social Media Executive, but keep short acronyms like SPH, AI, IT."""
    if not text.isupper():
        return text
    def acronym(w):
        return w.isalpha() and w not in SMALL_WORDS and (len(w) <= 2 or not re.search("[AEIOU]", w))
    return " ".join(w if acronym(w) else w.capitalize() for w in text.split())


def nice(name):
    n = re.sub(r"\((s|singapore|sg|pte\.?)\)", "", name, flags=re.I)
    n = re.sub(r"\b(pte|ltd|limited|private|singapore|llp|inc|llc|gmbh)\b\.?", "", n, flags=re.I)
    n = re.sub(r"\s+", " ", n).strip(" .,")
    return smart_case(n) or name


def slug(name):
    s = re.sub(r"\b(sg|com|www)\b", "", nice(name).lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:30] or "lead"


def opener(c, cfg):
    b = cfg["business"]
    rn = c["routes"][0]
    route = cfg["routes"][rn]
    link = b["enquiry_link"].replace("{src}", slug(c["company"]))
    if c["roles"]:
        role = smart_case(re.sub(r"\s*[\[(#].*$", "", c["roles"][0]).strip())
        art = "an" if role[:1].lower() in "aeiou" else "a"
        if route.get("priority"):
            hook = (f"I saw {nice(c['company'])} is hiring {art} {role}, "
                    f"so {route['priority']} looks like a priority this year.")
        else:
            hook = f"I saw {nice(c['company'])} is hiring {art} {role}."
    else:
        hook = f"I came across {nice(c['company'])}."
    proof = (" " + b["proof"].strip()) if b.get("proof") else ""
    cta = b.get("call_to_action", "If that could help, tell us what you need here")
    msg = f"Hi {{first name}}, {hook} {route['offer'].strip()}{proof} {cta}: {link}"
    return route["label"], link, msg


# ---------- run ----------

def main():
    ap = argparse.ArgumentParser(description="Find companies to reach out to, ranked, with an opener each.")
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--max", type=int, help="how many companies to read (overrides max_companies)")
    ap.add_argument("--fresh", action="store_true", help="re-read every website instead of using the cache")
    a = ap.parse_args()
    cfg = load_config(a.config)
    maxn = a.max or cfg["max_companies"]
    out_dir = os.path.join(HERE, cfg.get("output_dir", "output"))
    os.makedirs(os.path.join(out_dir, "history"), exist_ok=True)
    biz = cfg["business"]["name"]

    print(f"1/4 finding companies that need what {biz} sells...")
    cos = []
    country = str(cfg["business"].get("country", "")).strip().lower()
    if cfg.get("use_job_board", country == "singapore"):
        cos += job_board_signals(cfg)
        print(f"   job board: {len(cos)} companies with a website")
    extra = extra_signals(cfg)
    if extra:
        print(f"   your list: {len(extra)} sites")
    cos += extra
    if not cos:
        sys.exit("No companies found. Outside Singapore, add homepage URLs to extra_sites.txt "
                 "(one per line), or ask Claude to fill it for you.")
    sz = cfg["size"]
    size_pts = lambda e: 4 if (e or 0) >= sz["big"] else 2 if (e or 0) >= sz["mid"] else 0
    pre = lambda c: (min(len(c["roles"]), 3) * 3 if c["roles"] else 3) + size_pts(c.get("employees")) + \
        sum(cfg["routes"][rn]["bonus"] for rn in c["routes"] if c["roles"])
    cos.sort(key=lambda c: -pre(c))
    cos = cos[:maxn]
    print(f"   reading the top {len(cos)}")

    print(f"2/4 reading their websites with {MODEL} (about 5 to 60 s each)...")
    cache_path = os.path.join(out_dir, "site_cache.json")
    cache = {} if a.fresh or not os.path.exists(cache_path) else json.load(open(cache_path))
    for i, c in enumerate(cos, 1):
        t, cached = time.time(), c["website"] in cache
        try:
            c["site"] = scrape(c["website"], cache, cache_path)
            took = "cached" if cached else f"{time.time() - t:.0f} s"
            print(f"   ok   {i}/{len(cos)} {c['company']} ({took})")
        except Exception as e:
            c["site"] = {}
            print(f"   skip {i}/{len(cos)} {c['company']}: {str(e)[:80]}")

    print("3/4 scoring...")
    for c in cos:   # sites from your list: use the name the website gives itself
        name = (c.get("site") or {}).get("company_name")
        if c["source"] == "your list" and isinstance(name, str) and not blank(name) and len(name) < 60:
            c["company"] = name.strip()
    for c in cos:
        c["score"], c["why"] = score(c, cfg)
    cos.sort(key=lambda c: -c["score"])

    csv_path = os.path.join(out_dir, "all_leads.csv")
    before = set()
    if os.path.exists(csv_path):
        before = {r["company"] for r in csv.DictReader(open(csv_path))}
    fields = ["rank", "score", "company", "website", "employees", "roles", "job_link", "posted", "source", "route", "why",
              "contact_email", "contact_page", "linkedin", "form_link", "opener"]
    rows = []
    for i, c in enumerate(cos, 1):
        route, link, msg = opener(c, cfg)
        em, pg, li = contact(c)
        rows.append({"rank": i, "score": c["score"], "company": c["company"], "website": c["website"],
                     "employees": c.get("employees") or "", "roles": "; ".join(c["roles"]),
                     "job_link": c.get("job_link", ""), "posted": c.get("posted", ""), "source": c["source"], "route": route,
                     "why": "; ".join(c["why"]), "contact_email": em, "contact_page": pg, "linkedin": li,
                     "form_link": link, "opener": msg})
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print("4/4 writing the top 10...")
    md = [f"# {biz}: top 10 to reach out to", f"Run {time.strftime('%d %b %Y %H:%M')}, model {MODEL}", "",
          "Send each message yourself, one by one. Check the company and the person before you send.",
          "Scores run up to about 22. 10 or more is worth a look. Replace {first name} before you send.", ""]
    top = [r for r in rows if r["score"] > 0][:10]
    for n, r in enumerate(top, 1):
        new = "" if not before or r["company"] in before else " NEW"
        md += [f"## {n}. {nice(r['company'])} (score {r['score']}){new}",
               f"- Site: {r['website']}",
               f"- Why: {r['why']}"]
        if r["job_link"]:
            md.append(f"- Job ad: {r['job_link']}" + (f" (newest ad posted {r['posted']})" if r["posted"] else ""))
        md += [f"- Offer: {r['route']}",
               f"- Reach them: {r['contact_email'] or r['contact_page'] or r['linkedin'] or 'find the right person on LinkedIn'}",
               f"- Form link: {r['form_link']}", "", "> " + r["opener"], ""]
    if not top:
        md.append("No company scored above 0 this run. Try a bigger --max, or loosen skip_words in config.yaml.")
    text = "\n".join(md)
    open(os.path.join(out_dir, "top10.md"), "w").write(text)
    open(os.path.join(out_dir, "history", time.strftime("top10-%Y-%m-%d.md")), "w").write(text)
    rel = os.path.relpath(out_dir, os.getcwd())
    rel = out_dir if rel.startswith("..") else rel
    print(f"done: {rel}/top10.md ({len(top)} leads) and {rel}/all_leads.csv ({len(rows)} rows)")


if __name__ == "__main__":
    main()
