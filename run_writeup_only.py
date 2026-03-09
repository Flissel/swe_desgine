"""Run only the writeup phase on existing experiment results."""
import os
import sys
import shutil
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    os.system("chcp 65001 > nul 2>&1")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ["TERM"] = "xterm-256color"

from ai_scientist.perform_plotting import aggregate_plots
from ai_scientist.perform_icbinb_writeup import (
    perform_writeup as perform_icbinb_writeup,
    gather_citations,
)
from ai_scientist.perform_llm_review import perform_review, load_paper
from ai_scientist.llm import create_client
from ai_scientist.perform_vlm_review import perform_imgs_cap_ref_review
from ai_scientist.utils.token_tracker import token_tracker
import json

# Config
IDEA_DIR = "experiments/2026-03-03_13-49-27_compositional_regularization_nn_attempt_0"
MODEL_AGG_PLOTS = "openrouter/google/gemini-3-flash-preview"
MODEL_WRITEUP = "openrouter/anthropic/claude-sonnet-4"
MODEL_WRITEUP_SMALL = "openrouter/google/gemini-3-flash-preview"
MODEL_CITATION = "openrouter/google/gemini-3-flash-preview"
MODEL_REVIEW = "openrouter/anthropic/claude-sonnet-4"
NUM_CITE_ROUNDS = 20
WRITEUP_RETRIES = 3

os.environ["AI_SCIENTIST_ROOT"] = os.path.dirname(os.path.abspath(__file__))

# Step 1: Copy experiment_results to top-level if needed
experiment_results_src = os.path.join(IDEA_DIR, "logs/0-run/experiment_results")
experiment_results_dst = os.path.join(IDEA_DIR, "experiment_results")

if not os.path.exists(experiment_results_dst):
    print(f"Copying experiment results to {experiment_results_dst}...")
    shutil.copytree(experiment_results_src, experiment_results_dst, dirs_exist_ok=True)

# Step 2: Aggregate plots
print("Aggregating plots...")
aggregate_plots(base_folder=IDEA_DIR, model=MODEL_AGG_PLOTS)

# Clean up copied experiment_results
if os.path.exists(experiment_results_dst):
    shutil.rmtree(experiment_results_dst)

# Step 3: Save token tracker
with open(os.path.join(IDEA_DIR, "token_tracker.json"), "w") as f:
    json.dump(token_tracker.get_summary(), f)

# Step 4: Gather citations
print("Gathering citations...")
citations_text = gather_citations(
    IDEA_DIR,
    num_cite_rounds=NUM_CITE_ROUNDS,
    small_model=MODEL_CITATION,
)

# Step 5: Writeup (ICBINB 4-page format)
writeup_success = False
for attempt in range(WRITEUP_RETRIES):
    print(f"Writeup attempt {attempt+1} of {WRITEUP_RETRIES}")
    writeup_success = perform_icbinb_writeup(
        base_folder=IDEA_DIR,
        small_model=MODEL_WRITEUP_SMALL,
        big_model=MODEL_WRITEUP,
        page_limit=4,
        citations_text=citations_text,
    )
    if writeup_success:
        break

if not writeup_success:
    print("Writeup did not complete successfully after all retries.")
else:
    print("Writeup completed successfully!")

# Save final token tracker
with open(os.path.join(IDEA_DIR, "token_tracker.json"), "w") as f:
    json.dump(token_tracker.get_summary(), f)
with open(os.path.join(IDEA_DIR, "token_tracker_interactions.json"), "w") as f:
    json.dump(token_tracker.get_interactions(), f)

# Step 6: Review
import re
pdf_files = [f for f in os.listdir(IDEA_DIR) if f.endswith(".pdf")]
if pdf_files:
    reflection_pdfs = [f for f in pdf_files if "reflection" in f]
    if reflection_pdfs:
        final_pdfs = [f for f in reflection_pdfs if "final" in f.lower()]
        if final_pdfs:
            pdf_path = os.path.join(IDEA_DIR, final_pdfs[0])
        else:
            reflection_nums = []
            for f in reflection_pdfs:
                match = re.search(r"reflection[_.]?(\d+)", f)
                if match:
                    reflection_nums.append((int(match.group(1)), f))
            if reflection_nums:
                highest = max(reflection_nums, key=lambda x: x[0])
                pdf_path = os.path.join(IDEA_DIR, highest[1])
            else:
                pdf_path = os.path.join(IDEA_DIR, reflection_pdfs[0])
    else:
        pdf_path = os.path.join(IDEA_DIR, pdf_files[0])

    print(f"Reviewing paper: {pdf_path}")
    paper_content = load_paper(pdf_path)
    client, client_model = create_client(MODEL_REVIEW)
    review_text = perform_review(paper_content, client_model, client)
    review_img_cap_ref = perform_imgs_cap_ref_review(client, client_model, pdf_path)
    with open(os.path.join(IDEA_DIR, "review_text.txt"), "w") as f:
        f.write(json.dumps(review_text, indent=4))
    with open(os.path.join(IDEA_DIR, "review_img_cap_ref.json"), "w") as f:
        json.dump(review_img_cap_ref, f, indent=4)
    print("Paper review completed!")
else:
    print("No PDF found for review.")

print("Done!")
