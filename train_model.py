import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score


df = pd.read_csv("data/training_matches_synced.csv")

# Creating custom variables
df["log_point_diff"] = np.log(df["a_points"]) - np.log(df["b_points"])
df["point_ratio"] = df["a_points"] / df["b_points"]
round_map = {"Round of 32": 1, "Round of 16": 2, "Quarterfinal": 3, "Semifinal": 4, "Final": 5}
df["round_ord"] = df["round"].map(round_map)
            
# Train-test split
df["match_date"] = pd.to_datetime(df["match_date"])
train = df[df["match_date"] < "2024-05-01"]   # Jan–Apr: train
test  = df[df["match_date"] >= "2024-05-01"]  # May–Jun: test

print(df.columns.tolist())

# combine both features into one model
features = ["log_point_diff", "round_ord"]

x_train = train[features].values
x_test = test[features].values
y_train = train["winner"].values
y_test = test["winner"].values

scaler = StandardScaler()
x_train_scaled = scaler.fit_transform(x_train)
x_test_scaled = scaler.transform(x_test)

model = LogisticRegression()
model.fit(x_train_scaled, y_train)

preds = model.predict(x_test_scaled)
probs = model.predict_proba(x_test_scaled)[:, 1]

print(f"Accuracy: {accuracy_score(y_test, preds):.4f}")
print(f"AUC:      {roc_auc_score(y_test, probs):.4f}")