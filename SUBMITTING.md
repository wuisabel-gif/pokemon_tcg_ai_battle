# Submitting your agent to Kaggle

The competition (`pokemon-tcg-ai-battle`) does **not** take a plain file upload.
You submit a **Kaggle notebook** that builds `submission.tar.gz`, then click
**Submit Agent**. The tarball must contain exactly three things at its root:

```
submission.tar.gz
├── main.py      # your agent (submission/main.py in this repo)
├── deck.csv     # your deck (submission/deck.csv)
└── cg/          # the game engine (from the kiyotah/cg-lib dataset)
```

## Easiest path — fork the sample notebook

1. Open the competition → **Code** tab → **"A Sample Rule-Based Agent Mega Lucario ex Deck"**.
2. Click **Copy & Edit** (forks it into your account, already wired to the `cg-lib`
   dataset and the deck).
3. Replace the contents of the `%%writefile main.py` cell with your edited
   `submission/main.py`, and the deck cell / `deck.csv` with your `submission/deck.csv`.
4. **Run All** → it produces `submission.tar.gz`.
5. **Save Version** (commit the notebook).
6. Competition page → **Submit Agent** → pick your notebook → submit.

## Notebook packaging cell (reference)

This is the cell that builds the tarball (from the sample):

```python
import glob, os, tarfile
with tarfile.open("submission.tar.gz", "w:gz") as tar:
    tar.add("main.py", arcname="main.py")
    tar.add(glob.glob('/kaggle/input/**/cg-lib/cg', recursive=True)[0], arcname="cg")
    tar.add(glob.glob('/kaggle/input/datasets/**/deck.csv', recursive=True)[0], arcname="deck.csv")
os.remove('main.py')
```

If you embed `deck.csv` directly in the notebook with `%%writefile deck.csv`, you can
`tar.add("deck.csv", arcname="deck.csv")` instead of globbing a dataset.

## Submission limits

Check the competition **Rules** tab for the daily submission limit before you burn
attempts — iterate locally with `./tools/test_local.sh` first.
