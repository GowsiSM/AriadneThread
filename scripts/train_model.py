import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    average_precision_score
)

from xgboost import XGBClassifier
import joblib


# -----------------------------------
# 1. LOAD DATA
# -----------------------------------

print("Loading dataset...")

df = pd.read_csv("data/fraudTrain.csv")

print("Original shape:", df.shape)


# -----------------------------------
# 2. LIMIT DATASET FOR LAPTOP
# -----------------------------------

# Keep a manageable amount for first experiment
df = df.sample(
    n=min(400000, len(df)),
    random_state=42
)

print("Working shape:", df.shape)


# -----------------------------------
# 3. TIME FEATURES
# -----------------------------------

df["trans_date_trans_time"] = pd.to_datetime(
    df["trans_date_trans_time"]
)

df["hour"] = df["trans_date_trans_time"].dt.hour
df["day_of_week"] = df["trans_date_trans_time"].dt.dayofweek
df["month"] = df["trans_date_trans_time"].dt.month

df["is_night"] = (
    (df["hour"] >= 22) |
    (df["hour"] <= 5)
).astype(int)


# -----------------------------------
# 4. AMOUNT FEATURES
# -----------------------------------

df["log_amount"] = np.log1p(df["amt"])


# -----------------------------------
# 5. CUSTOMER FREQUENCY
# -----------------------------------

df["customer_frequency"] = (
    df.groupby("cc_num")["cc_num"]
      .transform("count")
)


# -----------------------------------
# 6. MERCHANT FREQUENCY
# -----------------------------------

df["merchant_frequency"] = (
    df.groupby("merchant")["merchant"]
      .transform("count")
)


# -----------------------------------
# 7. SELECT FEATURES
# -----------------------------------

features = [
    "amt",
    "log_amount",
    "hour",
    "day_of_week",
    "month",
    "is_night",
    "lat",
    "long",
    "merch_lat",
    "merch_long",
    "city_pop",
    "customer_frequency",
    "merchant_frequency",
    "category"
]

X = df[features]
y = df["is_fraud"]


# -----------------------------------
# 8. TRAIN / TEST SPLIT
# -----------------------------------

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)


# -----------------------------------
# 9. ENCODE CATEGORY
# -----------------------------------

categorical_features = ["category"]

numeric_features = [
    col for col in features
    if col not in categorical_features
]

preprocessor = ColumnTransformer(
    transformers=[
        (
            "category",
            OneHotEncoder(
                handle_unknown="ignore"
            ),
            categorical_features
        )
    ],
    remainder="passthrough"
)


X_train_processed = preprocessor.fit_transform(X_train)
X_test_processed = preprocessor.transform(X_test)


# -----------------------------------
# 10. TRAIN XGBOOST
# -----------------------------------

print("Training XGBoost...")

model = XGBClassifier(
    n_estimators=300,
    max_depth=6,
    learning_rate=0.08,
    subsample=0.8,
    colsample_bytree=0.8,
    objective="binary:logistic",
    eval_metric="aucpr",
    n_jobs=4,
    random_state=42
)

model.fit(
    X_train_processed,
    y_train
)


# -----------------------------------
# 11. PREDICTION
# -----------------------------------

probabilities = model.predict_proba(
    X_test_processed
)[:, 1]

predictions = (
    probabilities >= 0.5
).astype(int)


# -----------------------------------
# 12. EVALUATION
# -----------------------------------

print("\nClassification Report:")
print(
    classification_report(
        y_test,
        predictions
    )
)

roc_auc = roc_auc_score(
    y_test,
    probabilities
)

pr_auc = average_precision_score(
    y_test,
    probabilities
)

print("ROC-AUC:", roc_auc)
print("PR-AUC:", pr_auc)


# -----------------------------------
# 13. SAVE MODEL
# -----------------------------------

joblib.dump(
    model,
    "fraud_model.pkl"
)

joblib.dump(
    preprocessor,
    "preprocessor.pkl"
)

print("\nModel saved!")