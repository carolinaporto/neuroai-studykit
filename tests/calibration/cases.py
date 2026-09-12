"""Frozen calibration snapshot for the grader (`apps/api/services/grading.py`).

This is the item + rubric shown to the project owner for the first manual grader
calibration (M4), and the four hand-written answers they judged point-by-point against it
on 2026-09-12 ("Os quatro resultados bateram com o que eu esperava, ponto por ponto.
Corretor aprovado."). `tests/calibration/run_calibration.py` replays these four answers
against the real running API and compares against `expected_score`/`expected_covered`
below — see CLAUDE.md for when to re-run it.

Do not edit CHUNK_TEXT/RUBRIC/CASES to make a failing run pass — if the grader's behavior
changed, that's exactly what this fixture exists to catch. Only replace it wholesale when
the owner does a new, deliberate calibration pass and approves the new numbers.
"""

from dataclasses import dataclass

ITEM_PROMPT = (
    "Describe how a model's parameters are updated during one step of the optimization "
    "process, including the role of the loss function and the direction of movement."
)

REFERENCE_ANSWER = (
    "A loss function measures how wrong the model's predictions are on a batch of "
    "examples. The gradient of the loss with respect to each parameter points in the "
    "direction of steepest increase in the loss. Each update step moves the parameters a "
    "small distance in the opposite direction of the gradient, scaled by a learning rate, "
    "so that the loss decreases."
)

# Verbatim text of the real week-91 chunk this item was generated from (5 merged slides).
CHUNK_TEXT = """What Is Machine Learning?

A program that improves at a task from experience (data), instead of following only hand-written rules.
Three broad families: supervised, unsupervised, and reinforcement learning.
Performance is measured on data the model did not train on, not on the training set.

Notes: Emphasize the contrast with classical programming: in ML the data and the desired output are given, and the program (the model's parameters) is what gets produced.

Supervised vs. Unsupervised

Supervised learning: every training example has a label; regression predicts a number, classification predicts a category.
Unsupervised learning: no labels; the goal is to find structure, such as clusters or a lower-dimensional representation.
Semi-supervised and self-supervised methods use a small labeled set plus a large unlabeled set.

Gradient Descent

A loss function measures how wrong the model's predictions are on a batch of examples.
The gradient of the loss with respect to each parameter points in the direction of steepest increase.
Each step moves the parameters a small distance in the opposite direction, scaled by a learning rate.
Too large a learning rate overshoots and diverges; too small converges too slowly.

Notes: Stochastic gradient descent computes the gradient on a small random batch instead of the full dataset each step, which is noisier per step but far cheaper, and the noise itself can help escape shallow local minima.

Backpropagation

Chain rule applied layer by layer.
Reuses intermediate values from the forward pass.

Overfitting and Regularization

A model overfits when it fits the noise in the training set and its performance on held-out data gets worse even as training loss keeps improving.
Regularization techniques (L2 weight penalties, dropout, early stopping) trade a bit of training performance for better generalization.
A validation set, separate from both training and test data, is used to choose these hyperparameters without leaking information from the test set.

Notes: Early stopping means halting training when validation loss stops improving, even if training loss would keep going down -- the gap between the two curves is the signature of overfitting."""

CHUNK_LOCATORS = [
    {"slide": 1, "has_notes": True},
    {"slide": 2, "has_notes": False},
    {"slide": 3, "has_notes": True},
    {"slide": 4, "has_notes": False},
    {"slide": 5, "has_notes": True},
]

RUBRIC = [
    {
        "id": "p1",
        "point": "The loss function measures how wrong the model's predictions are.",
        "weight": 1.0,
        "support_quote": "A loss function measures how wrong the model's predictions are "
        "on a batch of examples.",
    },
    {
        "id": "p2",
        "point": "The gradient points in the direction of steepest increase of the loss.",
        "weight": 1.0,
        "support_quote": "The gradient of the loss with respect to each parameter points "
        "in the direction of steepest increase.",
    },
    {
        "id": "p3",
        "point": "Parameters move in the opposite direction of the gradient.",
        "weight": 1.5,
        "support_quote": "Each step moves the parameters a small distance in the opposite "
        "direction, scaled by a learning rate.",
    },
    {
        "id": "p4",
        "point": "The step size is scaled by a learning rate.",
        "weight": 1.0,
        "support_quote": "Each step moves the parameters a small distance in the opposite "
        "direction, scaled by a learning rate.",
    },
]

TOTAL_WEIGHT = sum(p["weight"] for p in RUBRIC)  # 4.5


@dataclass(frozen=True)
class CalibrationCase:
    label: str
    response_text: str
    expected_score: float
    expected_covered: dict[str, bool]


CASES = [
    CalibrationCase(
        label="A",
        response_text=(
            "The loss function tells you how far off the model's predictions are on the "
            "examples you showed it. You then compute the gradient of that loss with "
            "respect to each parameter — the gradient points toward whatever change would "
            "make the loss go up the fastest. Since you want the loss to go down, you move "
            "each parameter the other way, against the gradient, and how big that move is "
            "depends on the learning rate."
        ),
        expected_score=(1.0 + 1.0 + 1.5 + 1.0) / TOTAL_WEIGHT,
        expected_covered={"p1": True, "p2": True, "p3": True, "p4": True},
    ),
    CalibrationCase(
        label="B",
        response_text=(
            "The loss function measures how wrong the model's predictions are on the "
            "training examples. You then compute the gradient of the loss with respect to "
            "each parameter, which tells you the direction in which the loss increases "
            "most steeply."
        ),
        expected_score=(1.0 + 1.0) / TOTAL_WEIGHT,
        expected_covered={"p1": True, "p2": True, "p3": False, "p4": False},
    ),
    CalibrationCase(
        label="C",
        response_text="I don't really remember. Something about the gradient and adjusting the weights.",
        expected_score=0.0 / TOTAL_WEIGHT,
        expected_covered={"p1": False, "p2": False, "p3": False, "p4": False},
    ),
    CalibrationCase(
        label="D",
        response_text=(
            "The loss function measures how wrong the model's predictions are. The "
            "gradient points in the direction where the loss decreases most steeply, so "
            "each step moves the parameters along the gradient, in the same direction it "
            "points, which is what drives the loss down. The size of that step is scaled "
            "by the learning rate."
        ),
        expected_score=(1.0 + 1.0) / TOTAL_WEIGHT,
        expected_covered={"p1": True, "p2": False, "p3": False, "p4": True},
    ),
]
