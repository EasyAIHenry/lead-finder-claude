# Instructions for Claude Code in this repo

The person who opened this folder wants a ranked list of companies to reach out to. Many of them have never used a terminal. Explain each step in one plain sentence before you run it, and ask before anything that installs software outside this folder.

## 1. Set up

Check each item, fix what is missing, and say what you found.

1. **Python 3.12 or newer.** ScrapeGraphAI 2.x needs it. On a Mac, `python3` is often Apple's 3.9, and `pip install scrapegraphai` there silently installs the old 1.20.1. Never use it.
   - Mac or Linux: run `./scripts/setup.sh`. It uses `uv` if present, then Homebrew Python 3.12+, and refuses anything older.
   - If neither exists, ask before installing uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`), then run the script again.
   - Windows: `uv venv --python 3.12 .venv`, then `uv pip install --python .venv -r requirements.txt`, then `.venv\Scripts\python -m playwright install chromium`.
2. **Playwright Chromium.** `setup.sh` installs it. If a run says `Executable doesn't exist`, run `.venv/bin/python -m playwright install chromium`.
3. **Ollama.** Check with `ollama --version` and `curl -s http://localhost:11434/api/tags`.
   - Not installed: on a Mac with Homebrew, ask, then `brew install --cask ollama` and open the app once. Otherwise ask the person to download it from https://ollama.com and open it, and wait.
   - Not running: ask the person to open the Ollama app, or run `ollama serve` in the background.
4. **The model.** `ollama pull qwen2.5:7b-instruct` (4.7 GB). Tell the person it is a one-time download. On a computer with 8 GB of memory or less, offer `llama3.2` (2 GB) instead: faster, weaker, and set `LEAD_MODEL=ollama/llama3.2` when you run.

## 2. Fill config.yaml from four questions

Ask these one at a time and wait for each answer:

1. What is your business called, and what does it do?
2. What do you sell, and to whom? (If they sell more than one thing, get one line per thing.)
3. Which country are your customers in?
4. What is the link to your enquiry form or booking page?

Then copy `config.example.yaml` to `config.yaml` and change it:

- `business.name`, `business.country`, `business.proof` (ask for one real result they can stand behind, or leave it `""`; never invent one), `business.call_to_action`.
- `business.enquiry_link`: their link with `src={src}` added (`?src={src}`, or `&src={src}` if it already has a `?`). Keep any `#anchor` at the end. Tell them to add a hidden field called `src` to their form so each enquiry shows the lead it came from.
- `routes`: one route per thing they sell. For each, write a one-sentence `offer` in their words (plain, no hype, no exclamation marks), pick job-board `searches` that signal a company needs it, and write a `title_regex` that only real matching job titles pass. Give the strongest buying signal a `bonus` of 3.
- `skip_words` and `competitor_words`: add their own competitors (for example, a video studio adds "production", "studio", "film").
- `good_industries`: the industries they sell to.
- Delete the example values. Nothing about "Brightpath AI Studio" should remain.

Show them the finished `config.yaml` in plain words (not YAML) and ask if it looks right.

**Outside Singapore** the job board does not apply. Help them fill `extra_sites.txt` (copy from `extra_sites.example.txt`): ask what kind of company buys from them and in which city, then list up to 40 real company homepages, one per line. Only list sites you are confident exist, open each one with a quick request to check it loads, and drop any that fail. Say this list is a starting point they should check.

## 3. Run

- First a test: `.venv/bin/python lead_finder.py --max 3` (about 1 to 2 minutes).
- Then the full run: `.venv/bin/python lead_finder.py` (5 to 60 seconds per site, so 40 sites is about 15 to 20 minutes). Run it in the background and tell them roughly when it will finish.
- Other model: `LEAD_MODEL=ollama/llama3.2 .venv/bin/python lead_finder.py`.
- Re-read every site: add `--fresh`.

## 4. Read the results with them

Open `output/top10.md`. For each lead, say in one line why it is there, what the best contact route is, and anything that looks wrong (a competitor, an empty site, a company that is too small). Offer to add competitors to `skip_words` and run again. `output/all_leads.csv` has every company, including the ones that scored 0 or less and why.

## 5. Safety and sending rules

- **Never send an email, DM, form or message yourself**, even if asked. Do not connect mail or social accounts for sending. Your job ends at a list and a draft. The person sends each message by hand.
- You may help them rewrite an opener for one specific lead.
- Only use information the company publishes itself. Do not look up personal emails or phone numbers of individuals.
- Remind them before they send: one by one, never a mail-merge of the whole list. In Singapore, bulk commercial email (over 100 similar messages in 24 hours) needs `<ADV>` at the start of the subject, real sender details and a working unsubscribe, and Singapore phone numbers must be checked against the Do Not Call registry. In the UK, sole traders and partnerships need consent before a marketing email. This is general information, not legal advice.
- Never put API keys, passwords or personal data into this repo, a commit, or a chat message. `config.yaml`, `extra_sites.txt` and `output/` are git-ignored on purpose.

## 6. Run it every weekday (only if they ask)

Offer the launchd or cron example from README.md, filled in with their real folder path, or a scheduled task in the Claude desktop app. Tell them the computer must be awake and Ollama running at that time, and that a missed run does not catch up.
