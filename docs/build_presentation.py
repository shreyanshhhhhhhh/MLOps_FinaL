"""Build docs/PriceOptima_Presentation.pptx. Run from the repo root."""

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

NAVY = RGBColor(0x0B, 0x1F, 0x3A)
TEAL = RGBColor(0x0F, 0x6E, 0x6E)
GOLD = RGBColor(0xB0, 0x84, 0x2F)
CREAM = RGBColor(0xF6, 0xF3, 0xEC)
INK = RGBColor(0x1C, 0x24, 0x33)
MUTED = RGBColor(0x5C, 0x6B, 0x7A)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
CARD = RGBColor(0xFF, 0xFF, 0xFF)
PALE = RGBColor(0xE7, 0xEE, 0xEA)
LINE = RGBColor(0xD5, 0xDD, 0xD8)

W = Inches(13.333)
H = Inches(7.5)


def _set_run(run, text, size, bold, color, font="Calibri"):
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font


def add_text(slide, l, t, w, h, text, size=18, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(l, t, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    try:
        tf._txBody.bodyPr.set("anchor", {MSO_ANCHOR.TOP: "t", MSO_ANCHOR.MIDDLE: "ctr", MSO_ANCHOR.BOTTOM: "b"}[anchor])
    except Exception:
        pass
    lines = text.split("\n") if isinstance(text, str) else text
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(0)
        p.space_before = Pt(0)
        _set_run(p.add_run(), line, size, bold, color)
    return box


def rect(slide, l, t, w, h, fill, line_color=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, l, t, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line_color
    # no shadow
    sp_pr = shape._element.spPr
    effect = sp_pr.find(qn("a:effectLst"))
    if effect is not None:
        sp_pr.remove(effect)
    return shape


def rounded(slide, l, t, w, h, fill):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, l, t, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    # tighten corner
    try:
        shape.adjustments[0] = 0.08
    except Exception:
        pass
    return shape


def footer(slide, n, total, dark=False):
    color = RGBColor(0xC5, 0xD0, 0xC8) if dark else MUTED
    add_text(slide, Inches(0.55), Inches(7.12), Inches(9), Inches(0.28), "PriceOptima  ·  MLOps laboratory", 11, False, color)
    add_text(slide, Inches(11.2), Inches(7.12), Inches(1.6), Inches(0.28), f"{n}  /  {total}", 11, False, color, PP_ALIGN.RIGHT)


def new(prs, dark=False):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, 0, 0, W, H, NAVY if dark else CREAM)
    if not dark:
        rect(slide, 0, 0, Inches(0.12), H, TEAL)
    return slide


def build():
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    prs.core_properties.title = "PriceOptima"
    prs.core_properties.subject = "MLOps laboratory: dynamic retail pricing"
    total = 14

    # 1 title
    s = new(prs, dark=True)
    rect(s, 0, 0, Inches(0.18), H, GOLD)
    add_text(s, Inches(0.7), Inches(1.55), Inches(11), Inches(0.4), "MLOPS LABORATORY", 16, True, GOLD)
    add_text(s, Inches(0.7), Inches(2.05), Inches(12), Inches(1.2), "PriceOptima", 60, True, WHITE)
    add_text(s, Inches(0.7), Inches(3.35), Inches(11), Inches(1.1), "Predict monthly retail quantity.\nChoose the price that maximises profit.", 24, False, RGBColor(0xD5, 0xE4, 0xDE))
    add_text(s, Inches(0.7), Inches(5.5), Inches(11), Inches(0.8), "DVC pipeline   ·   MLflow   ·   FastAPI   ·   Docker   ·   GitHub Actions   ·   S3 and EC2", 16, False, RGBColor(0x9F, 0xB8, 0xB0))
    footer(s, 1, total, dark=True)

    # 2 aim
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.32), Inches(12), Inches(0.5), "Aim", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.95), Inches(2.2), Inches(0.06), GOLD)
    add_text(
        s,
        Inches(0.5),
        Inches(1.3),
        Inches(12.2),
        Inches(1.6),
        "Build a pricing service that predicts how many units a product will sell in a month, then searches a price grid and keeps the price with the highest profit.",
        22,
        False,
        INK,
    )
    points = [
        ("Predict", "Monthly quantity, column qty, from price and context."),
        ("Decide", "Score each candidate price. Profit is quantity times price minus cost."),
        ("Operate", "Version the data, track every model, serve one, and deploy it so it can be rolled back."),
    ]
    for i, (title, body) in enumerate(points):
        top = Inches(3.15 + i * 1.2)
        rounded(s, Inches(0.5), top, Inches(12.3), Inches(1.05), CARD)
        rect(s, Inches(0.5), top, Inches(0.1), Inches(1.05), TEAL)
        add_text(s, Inches(0.85), top + Inches(0.14), Inches(11.6), Inches(0.35), title, 18, True, TEAL)
        add_text(s, Inches(0.85), top + Inches(0.48), Inches(11.6), Inches(0.45), body, 16, False, INK)
    footer(s, 2, total)

    # 3 objectives
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.32), Inches(12), Inches(0.5), "Objectives", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.95), Inches(2.2), Inches(0.06), GOLD)
    objs = [
        ("01", "Pipeline", "One parameter file. Five DVC stages. A lock file that names every hash."),
        ("02", "Experiments", "Train 14 models. Log them in MLflow. Promote the lowest test RMSE."),
        ("03", "Honest test", "Hold out the last 4 months. Do not take 20% of the rows from every month."),
        ("04", "Serving", "FastAPI uses the same feature code as training. No second implementation."),
        ("05", "Packaging", "The Docker image has the code. It downloads the pickle when it starts."),
        ("06", "Cloud", "GitHub Actions checks the lock. S3 stores the model. EC2 runs the API."),
    ]
    for i, (num, title, body) in enumerate(objs):
        col = i % 3
        row = i // 3
        left = Inches(0.45 + col * 4.2)
        top = Inches(1.35 + row * 2.7)
        rounded(s, left, top, Inches(4.0), Inches(2.45), CARD)
        add_text(s, left + Inches(0.25), top + Inches(0.22), Inches(3.5), Inches(0.4), num, 18, True, GOLD)
        add_text(s, left + Inches(0.25), top + Inches(0.7), Inches(3.5), Inches(0.4), title, 22, True, NAVY)
        add_text(s, left + Inches(0.25), top + Inches(1.25), Inches(3.5), Inches(0.95), body, 15, False, INK)
    footer(s, 3, total)

    # 4 dataset
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.32), Inches(12), Inches(0.5), "Data and the split", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.95), Inches(2.2), Inches(0.06), GOLD)
    add_text(s, Inches(0.5), Inches(1.2), Inches(12), Inches(0.7), "Kaggle Retail Price Optimization. 676 product-months, 30 columns, January 2017 to August 2018. Target: qty.", 18, False, INK)
    headers = ["Part", "Months", "Rows"]
    rows = [
        ["Train", "16 months  ·  Jan 2017 – Apr 2018", "516"],
        ["Test", "4 months  ·  May 2018 – Aug 2018", "160"],
    ]
    table_shape = s.shapes.add_table(3, 3, Inches(0.5), Inches(2.1), Inches(12.3), Inches(1.8))
    table = table_shape.table
    table.columns[0].width = Inches(2.2)
    table.columns[1].width = Inches(7.6)
    table.columns[2].width = Inches(2.5)
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        for p in cell.text_frame.paragraphs:
            p.alignment = PP_ALIGN.LEFT
            for r in p.runs:
                r.font.size = Pt(14)
                r.font.bold = True
                r.font.color.rgb = WHITE
                r.font.name = "Calibri"
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.cell(i + 1, j)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if i == 0 else PALE
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(15)
                    r.font.color.rgb = INK
                    r.font.name = "Calibri"
                    r.font.bold = j == 0
    add_text(
        s,
        Inches(0.5),
        Inches(4.2),
        Inches(12.3),
        Inches(2.4),
        "test_size: 0.2 is 20% of the 20 distinct months, not 20% of the rows inside each month.\nA month stays entirely in train or entirely in test.\nThe test RMSE is computed once, on May–August 2018.\nThe live API does not recheck 20% of the data every month.",
        18,
        False,
        INK,
    )
    footer(s, 4, total)

    # 5 workflow
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.28), Inches(12), Inches(0.45), "Workflow", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.85), Inches(2.2), Inches(0.06), GOLD)
    stages = [
        ("1", "Preprocess", "Clean dates.\nCut the last\n4 months."),
        ("2", "Features", "Price vs\ncompetitors.\nFit preprocessor."),
        ("3", "Train", "14 models.\nLog every\nrun in MLflow."),
        ("4", "Evaluate", "Rank by\ntest RMSE.\nWrite plots."),
        ("5", "Select", "Promote\nmodel.pkl\nand the card."),
    ]
    for i, (num, title, body) in enumerate(stages):
        left = Inches(0.4 + i * 2.58)
        rounded(s, left, Inches(1.3), Inches(2.35), Inches(3.35), CARD)
        rect(s, left, Inches(1.3), Inches(2.35), Inches(0.12), TEAL)
        add_text(s, left + Inches(0.15), Inches(1.55), Inches(2.05), Inches(0.4), num, 20, True, GOLD)
        add_text(s, left + Inches(0.15), Inches(2.05), Inches(2.05), Inches(0.45), title, 18, True, NAVY)
        add_text(s, left + Inches(0.15), Inches(2.6), Inches(2.05), Inches(1.7), body, 15, False, INK)
        if i < 4:
            add_text(s, left + Inches(2.15), Inches(2.7), Inches(0.45), Inches(0.4), "›", 22, True, TEAL)
    add_text(s, Inches(0.5), Inches(4.9), Inches(12.3), Inches(1.8), "Command:  dvc repro\nA stage whose code, parameters, and inputs did not change is skipped.\nparams.yaml holds the settings.  dvc.yaml holds the steps.  dvc.lock holds the hashes.", 18, False, INK)
    footer(s, 5, total)

    # 6 three files
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.28), Inches(12), Inches(0.45), "Three files that control the pipeline", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.85), Inches(2.2), Inches(0.06), GOLD)
    cards = [
        ("params.yaml", "The settings", "Seed 42.\nChronological 20% split.\nDate format %d-%m-%Y.\nTarget qty.\nThe 14-model grid."),
        ("dvc.yaml", "The recipe", "Command, inputs,\nparameters, and outputs\nfor each of the five stages.\nNo data and no pickle\nlive in this file."),
        ("dvc.lock", "The proof", "MD5 of the code,\nthe parameters, and\nevery output.\nCI fails if this file\ndoes not match the run."),
    ]
    for i, (title, sub, body) in enumerate(cards):
        left = Inches(0.45 + i * 4.25)
        rounded(s, left, Inches(1.3), Inches(4.05), Inches(5.3), CARD)
        rect(s, left, Inches(1.3), Inches(4.05), Inches(0.12), TEAL if i < 2 else GOLD)
        add_text(s, left + Inches(0.25), Inches(1.6), Inches(3.55), Inches(0.45), title, 22, True, NAVY)
        add_text(s, left + Inches(0.25), Inches(2.15), Inches(3.55), Inches(0.4), sub, 16, True, TEAL)
        add_text(s, left + Inches(0.25), Inches(2.7), Inches(3.55), Inches(3.4), body, 16, False, INK)
    footer(s, 6, total)

    # 7 results
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.28), Inches(12), Inches(0.45), "Experiment results", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.85), Inches(2.2), Inches(0.06), GOLD)
    add_text(s, Inches(0.5), Inches(1.1), Inches(12), Inches(0.4), "MLflow experiment priceoptima-demand. Selection metric: test RMSE. Lower is better.", 16, False, MUTED)
    headers = ["Family", "Best setting", "Test RMSE", "Test R²"]
    data = [
        ["Gradient boosting", "100 trees, lr 0.05, depth 3", "7.53", "0.50"],
        ["Random forest", "100 trees, depth 16", "7.76", "0.47"],
        ["LightGBM", "100 trees, lr 0.1, 31 leaves", "7.83", "0.46"],
        ["Ridge", "alpha 10", "10.76", "−0.02"],
        ["Linear regression", "fit intercept", "10.99", "−0.06"],
    ]
    ts = s.shapes.add_table(6, 4, Inches(0.5), Inches(1.65), Inches(12.3), Inches(3.6))
    tbl = ts.table
    widths = [Inches(3.2), Inches(5.3), Inches(2.0), Inches(1.8)]
    for j, w in enumerate(widths):
        tbl.columns[j].width = w
    for j, htxt in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.text = htxt
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        for p in cell.text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(14)
                r.font.bold = True
                r.font.color.rgb = WHITE
                r.font.name = "Calibri"
    for i, row in enumerate(data):
        for j, val in enumerate(row):
            cell = tbl.cell(i + 1, j)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(0xE5, 0xF2, 0xEC) if i == 0 else WHITE
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(15)
                    r.font.bold = i == 0
                    r.font.color.rgb = INK
                    r.font.name = "Calibri"
    add_text(s, Inches(0.5), Inches(5.5), Inches(12.3), Inches(1.4), "Sample: bed product, May 2018, price 39.99. Recorded sales 19.\nGradient boosting predicts about 7.91.\nmodel-v1 is that boosting model. model-v2 is ridge, kept so a swap is visible.", 16, False, INK)
    footer(s, 7, total)

    # 8 architecture
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.28), Inches(12), Inches(0.45), "Where each piece lives", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.85), Inches(2.2), Inches(0.06), GOLD)
    blocks = [
        (Inches(0.45), "GitHub", "Code\ndvc.yaml\ndvc.lock\nparams.yaml\nCI workflow"),
        (Inches(3.55), "Actions", "lint\ntest\nlock check\ndocker build"),
        (Inches(6.65), "S3", "CSV and\nmodel hashes\nprivate bucket\neu-north-1"),
        (Inches(9.75), "EC2", "t3.micro\ncontainer\nport 8000\n/docs"),
    ]
    for left, title, body in blocks:
        rounded(s, left, Inches(1.4), Inches(2.9), Inches(3.5), CARD)
        rect(s, left, Inches(1.4), Inches(2.9), Inches(0.7), NAVY)
        add_text(s, left + Inches(0.15), Inches(1.52), Inches(2.6), Inches(0.45), title, 18, True, WHITE, PP_ALIGN.CENTER)
        add_text(s, left + Inches(0.2), Inches(2.25), Inches(2.5), Inches(2.4), body, 16, False, INK, PP_ALIGN.CENTER)
    add_text(s, Inches(0.5), Inches(5.15), Inches(12.3), Inches(1.7), "The image does not contain model.pkl.\nOn start, fetch_model.sh runs dvc pull from S3. The EC2 role can read the bucket. It cannot delete it.\n/health means the process is up. /ready means the model is loaded.", 17, False, INK)
    footer(s, 8, total)

    # 9 serving
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.28), Inches(12), Inches(0.45), "Serving and the price search", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.85), Inches(2.2), Inches(0.06), GOLD)
    rows = [
        ("GET /health", "The process is up."),
        ("GET /ready", "model.pkl, the preprocessor, and the model card are loaded."),
        ("GET /model-info", "Name, test RMSE, git commit, data hash."),
        ("POST /predict-demand", "Expected quantity at the price you send."),
        ("POST /optimize-price", "Best price on the grid. Profit if unit_cost is sent."),
        ("GET /docs", "The Swagger page used in the demonstration."),
    ]
    for i, (ep, desc) in enumerate(rows):
        top = Inches(1.2 + i * 0.9)
        rounded(s, Inches(0.5), top, Inches(12.3), Inches(0.78), CARD)
        add_text(s, Inches(0.75), top + Inches(0.18), Inches(4.3), Inches(0.45), ep, 16, True, TEAL)
        add_text(s, Inches(5.1), top + Inches(0.18), Inches(7.4), Inches(0.45), desc, 16, False, INK)
    footer(s, 9, total)

    # 10 CI
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.28), Inches(12), Inches(0.45), "CI, then the release path", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.85), Inches(2.2), Inches(0.06), GOLD)
    jobs = [("lint", "Ruff"), ("test", "Pytest"), ("lock", "dvc status"), ("build", "docker build")]
    for i, (name, sub) in enumerate(jobs):
        left = Inches(0.5 + i * 3.2)
        rounded(s, left, Inches(1.25), Inches(2.9), Inches(1.55), NAVY)
        add_text(s, left, Inches(1.45), Inches(2.9), Inches(0.5), name, 22, True, WHITE, PP_ALIGN.CENTER)
        add_text(s, left, Inches(2.05), Inches(2.9), Inches(0.45), sub, 16, False, RGBColor(0xD5, 0xE4, 0xDE), PP_ALIGN.CENTER)
        if i < 3:
            add_text(s, left + Inches(2.55), Inches(1.7), Inches(0.7), Inches(0.4), "→", 22, True, TEAL)
    notes = [
        "A failure stops the later jobs. The image is not built if the lock does not match.",
        "With no AWS secret, the lock check uses the dvc-storage folder in the repository.",
        "CD runs only after CI succeeds on main. It smoke-tests, scans, and deploys.",
        "deploy.sh waits 120 seconds for /ready. If that fails, it starts the previous image.",
    ]
    for i, note in enumerate(notes):
        add_text(s, Inches(0.55), Inches(3.15 + i * 0.85), Inches(12.2), Inches(0.7), note, 18, False, INK)
    footer(s, 10, total)

    # 11 model versions
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.28), Inches(12), Inches(0.45), "Two models, one image", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.85), Inches(2.2), Inches(0.06), GOLD)
    rounded(s, Inches(0.5), Inches(1.3), Inches(6.0), Inches(4.3), CARD)
    add_text(s, Inches(0.8), Inches(1.55), Inches(5.4), Inches(0.4), "model-v1", 22, True, TEAL)
    add_text(s, Inches(0.8), Inches(2.15), Inches(5.4), Inches(2.8), "Gradient boosting\n100 trees, learning rate 0.05, depth 3\nTest RMSE 7.53\nThis is the best experiment.", 18, False, INK)
    rounded(s, Inches(6.8), Inches(1.3), Inches(6.0), Inches(4.3), CARD)
    add_text(s, Inches(7.1), Inches(1.55), Inches(5.4), Inches(0.4), "model-v2", 22, True, GOLD)
    add_text(s, Inches(7.1), Inches(2.15), Inches(5.4), Inches(2.8), "Ridge, alpha 10\nTest RMSE 10.76\nWorse on purpose.\nThe current lock serves this one\nso a swap changes the answer.", 18, False, INK)
    add_text(s, Inches(0.5), Inches(5.8), Inches(12.3), Inches(1.1), "MODEL_VERSION selects a git tag. The container pulls that lock from S3.\nThe Docker image is not rebuilt.", 18, False, INK)
    footer(s, 11, total)

    # 12 mlops map
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.28), Inches(12), Inches(0.45), "MLOps ideas in this repository", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.85), Inches(2.2), Inches(0.06), GOLD)
    ideas = [
        ("Versioned data", "DVC hash in S3, pointer in Git"),
        ("Tracked experiments", "14 MLflow runs, one metric"),
        ("Promoted model", "model.pkl plus model_meta.json"),
        ("Same features", "src/features.py used by the API"),
        ("Immutable image", "Code in Docker, model outside it"),
        ("Automated check", "lint, test, lock, build"),
        ("Rollback", "previous image if /ready fails"),
        ("Readiness", "/ready is the deploy gate"),
    ]
    for i, (title, body) in enumerate(ideas):
        col = i % 4
        row = i // 4
        left = Inches(0.4 + col * 3.22)
        top = Inches(1.25 + row * 2.7)
        rounded(s, left, top, Inches(3.05), Inches(2.4), CARD)
        add_text(s, left + Inches(0.18), top + Inches(0.3), Inches(2.7), Inches(0.8), title, 16, True, NAVY)
        add_text(s, left + Inches(0.18), top + Inches(1.2), Inches(2.7), Inches(0.9), body, 14, False, INK)
    footer(s, 12, total)

    # 13 viva
    s = new(prs)
    add_text(s, Inches(0.5), Inches(0.28), Inches(12), Inches(0.45), "Questions worth answering", 32, True, NAVY)
    rect(s, Inches(0.5), Inches(0.85), Inches(2.2), Inches(0.06), GOLD)
    qas = [
        ("Why DVC, not only Git?", "Git holds code and dvc.lock. The pickle is stored by hash. A tag selects a lock."),
        ("Why is the model outside the image?", "A new model would otherwise mean a new image. MODEL_VERSION only changes the pull."),
        ("Why CI?", "Every change runs the same lint, tests, lock check, and image build."),
        ("What is not in this lab?", "No drift detector. Monitoring is /ready and a request counter. Say that plainly."),
    ]
    for i, (q, a) in enumerate(qas):
        top = Inches(1.15 + i * 1.4)
        add_text(s, Inches(0.5), top, Inches(12.2), Inches(0.4), q, 18, True, TEAL)
        add_text(s, Inches(0.5), top + Inches(0.42), Inches(12.2), Inches(0.7), a, 16, False, INK)
    footer(s, 13, total)

    # 14 close
    s = new(prs, dark=True)
    rect(s, 0, 0, Inches(0.18), H, GOLD)
    add_text(s, Inches(0.7), Inches(1.8), Inches(12), Inches(0.8), "What to remember", 20, True, GOLD)
    add_text(
        s,
        Inches(0.7),
        Inches(2.6),
        Inches(11.5),
        Inches(2.6),
        "A future-month test.\nFourteen tracked models.\nOne image, two model versions.\nThe model is pulled from S3 when the container starts.",
        26,
        False,
        WHITE,
    )
    add_text(s, Inches(0.7), Inches(5.6), Inches(11), Inches(0.5), "Report:  docs/PROJECT_REPORT.md", 16, False, RGBColor(0xD5, 0xE4, 0xDE))
    footer(s, 14, total, dark=True)

    out = "docs/PriceOptima_Presentation.pptx"
    prs.save(out)
    print(out, "slides", len(prs.slides))


if __name__ == "__main__":
    build()
