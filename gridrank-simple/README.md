# GridRank (simple version — for your own use)

Sort any Instagram creator's posts by **Most Views**, **Most Likes**, or **Most Comments**
right inside Instagram, filter by **count range** and **posted date**, and **export the
videos to Excel** ranked by a views+likes heat score. All features free, nothing locked.

This is the personal-use build: no paywall, no payment library, no account needed.

## How it works (and why it's reasonable)

Instagram's profile grid is a React app that constantly re-renders, so physically
rearranging it is fragile. Instead, GridRank quietly reads the data Instagram *itself*
loads while you scroll a profile (view counts, likes, comments, dates) and shows it in a
sortable side panel. It makes **zero extra network requests** — it only reads responses
your browser already received while you browse, logged in as yourself.

## Install (about 1 minute)

1. Unzip this folder somewhere permanent (e.g. `Documents/gridrank-simple`).
   Don't delete it later — Chrome loads it from this location.
2. Open Chrome → `chrome://extensions`.
3. Turn on **Developer mode** (top-right toggle).
4. Click **Load unpacked** and select the `gridrank-simple` folder.
5. Open Instagram. A "GridRank" panel appears top-right.

## Use

1. Go to a creator's profile, e.g. `https://www.instagram.com/<creator>/`.
2. Click the **Reels** tab (or scroll the grid) so Instagram loads the posts.
   GridRank only knows about posts you've actually scrolled past — scroll more for more.
3. Pick a sort: **Most Views / Most Likes / Most Comments**.
4. Optional filters:
   - **Range** — type min/max for the selected metric. Shorthand works: `10k`, `1.5m`, `2b`.
   - **Posted** — pick a date range. Leave either side blank for open-ended.
   - **Clear filters** resets everything.
5. The top 2 posts get a ★. Click any row to open it on Instagram.

## Export to Excel

Click **⬇ Export Excel** to download the current creator's **videos** in the active date
range as `gridrank_<creator>_<from>_to_<to>.xlsx`. Columns:

`Rank · Heat (0-100) · Views · Likes · Comments · Eng % · Posted · Caption · Link`

- **Heat score** = average of (views normalized 0-100) and (likes normalized 0-100) across
  the videos in your window — so big view counts don't drown out likes.
- Top 2 rows are starred (your "most working" videos for that creator/window).
- The Link column is clickable.

These .xlsx files are designed to feed the Kalinga app's research workflow — one file
per creator — but they're perfectly useful on their own too.

## Tips & limits

- **Scroll to collect.** 60 posts scrolled = 60 posts available. The panel count shows how
  many it has so far.
- **Views need video.** Image posts have no view count; the Excel export skips them.
- **If the panel disappears** after navigating, it re-adds itself within ~2 seconds.
- **Hide it** with the – button in the panel header.

## A note on staying out of trouble

This reads only what your own logged-in browser already loaded, and makes no extra
requests — that's the gentle approach. Still, automated collection of platform data sits
in a gray area of Instagram's terms. For private personal research this is low-risk;
just don't hammer it or redistribute scraped data. (General info, not legal advice.)
