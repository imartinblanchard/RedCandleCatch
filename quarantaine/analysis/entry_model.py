#!/usr/bin/env python3
"""
ML Model for ENTRY prediction - LONG Strategy (Gap & Go)

Uses features available at market OPEN (9:30) to predict:
- Should I enter this LONG trade?

Strategy: Gap & Go (Warrior Trading style)
- Entry: Break above pre-market high
- Stop: Below pre-market low (or 10% below entry)
- Target: 2:1 risk/reward ratio

WIN = Stock went UP from entry (close > entry) AND did not hit stop

Usage:
    python -m analysis.entry_model
    python -m analysis.entry_model --train
"""
import argparse
import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report
)
from sklearn.preprocessing import LabelEncoder

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
COMPUTED_DIR = DATA_DIR / 'computed'
MODELS_DIR = COMPUTED_DIR / 'models'

# Ensure models directory exists
MODELS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# PRE-ENTRY FEATURES (available at 9:30 OPEN - before trade)
# =============================================================================
PRE_ENTRY_FEATURES_NUMERIC = [
    # Gap
    'gap_pct',

    # Pre-market
    'pm_high_pct',
    'pm_low_pct',
    'pm_range_pct',
    'pm_volume',

    # Market context
    'fear_greed',
    'spy_change_pct',
    'vix_close',

    # Fundamentals
    'float_shares',
    'inst_pct',

    # Volume
    'relative_volume',

    # Date
    'day_of_week',
    'is_monday',
    'is_friday',
]

PRE_ENTRY_FEATURES_CATEGORICAL = [
    'gap_category',
    'pm_trend',
    'float_category',
    'volume_category',
    'catalyst_type',
    'sector',
]


class EntryModel:
    """Random Forest model for LONG entry prediction."""

    def __init__(self, strategy: str = 'momentum'):
        """
        Initialize entry model.

        Args:
            strategy: 'momentum' or 'pullback'
        """
        self.strategy = strategy
        self.features_file = COMPUTED_DIR / f'{strategy}-features.csv'
        self.model_file = MODELS_DIR / f'{strategy}-entry-model.joblib'
        self.encoders_file = MODELS_DIR / f'{strategy}-entry-encoders.joblib'

        self.model = None
        self.encoders = {}
        self.feature_columns = []

    def load_data(self) -> pd.DataFrame:
        """Load features data."""
        if not self.features_file.exists():
            raise FileNotFoundError(f"Features file not found: {self.features_file}")

        df = pd.read_csv(self.features_file)
        print(f"Loaded {len(df)} rows from {self.features_file.name}")
        return df

    def create_target(self, df: pd.DataFrame, stop_pct: float = 10.0) -> pd.DataFrame:
        """
        Create target variable for LONG trades.

        LONG Strategy:
        - WIN = Stock went UP (close_pct > 0) AND did not hit stop (low_pct > -stop)

        Args:
            df: DataFrame with features
            stop_pct: Stop loss percentage (below entry)
        """
        df = df.copy()

        # LONG: stopped if low_pct <= -stop_pct
        not_stopped = df['low_pct'] > -stop_pct
        profitable = df['close_pct'] > 0
        df['win'] = (not_stopped & profitable).astype(int)
        df['stopped'] = (~not_stopped).astype(int)

        win_count = df['win'].sum()
        loss_count = len(df) - win_count
        stopped_count = df['stopped'].sum()
        win_rate = win_count / len(df) * 100

        print(f"\nTarget variable created (LONG, stop at {stop_pct}%):")
        print(f"  WIN:     {win_count} ({win_rate:.1f}%)")
        print(f"  LOSS:    {loss_count} ({100-win_rate:.1f}%)")
        print(f"  Stopped: {stopped_count} ({stopped_count/len(df)*100:.1f}%)")

        return df

    def prepare_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """Prepare features for training."""
        # Select features that exist
        available_numeric = [f for f in PRE_ENTRY_FEATURES_NUMERIC if f in df.columns]
        available_categorical = [f for f in PRE_ENTRY_FEATURES_CATEGORICAL if f in df.columns]

        print(f"\nFeatures available for ENTRY prediction:")
        print(f"  Numeric: {len(available_numeric)}")
        print(f"  Categorical: {len(available_categorical)}")

        # Start with numeric features
        X = df[available_numeric].copy()

        # Encode categorical features
        for cat_col in available_categorical:
            if cat_col in df.columns:
                le = LabelEncoder()
                col_data = df[cat_col].fillna('unknown')
                X[cat_col] = le.fit_transform(col_data.astype(str))
                self.encoders[cat_col] = le

        # Fill NaN with median
        for col in X.columns:
            if X[col].isna().any():
                median_val = X[col].median()
                X[col] = X[col].fillna(median_val if pd.notna(median_val) else 0)

        self.feature_columns = list(X.columns)
        y = df['win']

        print(f"  Total features: {len(self.feature_columns)}")

        return X, y

    def train(self, test_size: float = 0.2, random_state: int = 42) -> Dict:
        """Train the Random Forest model."""
        # Load and prepare data
        df = self.load_data()
        df = self.create_target(df)
        X, y = self.prepare_features(df)

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )

        print(f"\nData split:")
        print(f"  Train: {len(X_train)} samples")
        print(f"  Test:  {len(X_test)} samples")

        # Train model
        print(f"\nTraining Random Forest for LONG ENTRY prediction...")
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            min_samples_split=5,
            min_samples_leaf=3,
            random_state=random_state,
            n_jobs=-1
        )

        self.model.fit(X_train, y_train)

        # Predictions
        y_pred = self.model.predict(X_test)

        # Metrics
        metrics = {
            'accuracy': accuracy_score(y_test, y_pred),
            'precision': precision_score(y_test, y_pred),
            'recall': recall_score(y_test, y_pred),
            'f1': f1_score(y_test, y_pred),
        }

        # Cross-validation
        cv_scores = cross_val_score(self.model, X, y, cv=5)
        metrics['cv_mean'] = cv_scores.mean()
        metrics['cv_std'] = cv_scores.std()

        # Print results
        print(f"\n{'='*60}")
        print(f"ENTRY MODEL RESULTS - {self.strategy.upper()} (LONG)")
        print(f"{'='*60}")
        print(f"\nTest Set Metrics:")
        print(f"  Accuracy:  {metrics['accuracy']:.1%}")
        print(f"  Precision: {metrics['precision']:.1%}")
        print(f"  Recall:    {metrics['recall']:.1%}")
        print(f"  F1 Score:  {metrics['f1']:.1%}")
        print(f"\nCross-Validation (5-fold):")
        print(f"  Mean: {metrics['cv_mean']:.1%} (+/- {metrics['cv_std']*2:.1%})")

        return metrics

    def get_feature_importance(self, top_n: int = 10) -> pd.DataFrame:
        """Get feature importance."""
        if self.model is None:
            raise ValueError("Model not trained yet")

        importance = pd.DataFrame({
            'feature': self.feature_columns,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)

        print(f"\n{'='*60}")
        print(f"TOP {top_n} FEATURE IMPORTANCE (ENTRY)")
        print(f"{'='*60}")

        for _, row in importance.head(top_n).iterrows():
            bar = '#' * int(row['importance'] * 50)
            print(f"  {row['feature']:<25} {row['importance']:.3f} {bar}")

        return importance

    def save(self):
        """Save model and encoders."""
        if self.model is None:
            raise ValueError("Model not trained yet")

        joblib.dump(self.model, self.model_file)
        joblib.dump({
            'encoders': self.encoders,
            'feature_columns': self.feature_columns,
        }, self.encoders_file)

        print(f"\nModel saved to: {self.model_file}")

    def load(self):
        """Load saved model."""
        if not self.model_file.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_file}")

        self.model = joblib.load(self.model_file)
        meta = joblib.load(self.encoders_file)
        self.encoders = meta['encoders']
        self.feature_columns = meta['feature_columns']

        print(f"Model loaded from: {self.model_file}")

    def predict(self, features: Dict) -> Tuple[int, float]:
        """
        Predict WIN/LOSS probability.

        Returns:
            (prediction, probability)
        """
        if self.model is None:
            raise ValueError("Model not trained or loaded")

        # Build feature vector
        X = pd.DataFrame([features])

        # Encode categoricals
        for cat_col, encoder in self.encoders.items():
            if cat_col in X.columns:
                val = X[cat_col].iloc[0]
                if val in encoder.classes_:
                    X[cat_col] = encoder.transform(X[cat_col].astype(str))
                else:
                    X[cat_col] = 0

        # Ensure all columns present
        for col in self.feature_columns:
            if col not in X.columns:
                X[col] = 0

        X = X[self.feature_columns]

        prediction = self.model.predict(X)[0]
        probability = self.model.predict_proba(X)[0, 1]

        return prediction, probability

    def recommend(self, features: Dict, threshold: float = 0.60) -> Dict:
        """
        Get entry recommendation.

        Args:
            features: Dict of pre-entry features
            threshold: Minimum WIN probability to recommend ENTER

        Returns:
            Dict with recommendation, probability, confidence
        """
        prediction, probability = self.predict(features)

        if probability >= threshold:
            recommendation = 'ENTER'
            confidence = 'HIGH' if probability >= 0.70 else 'MEDIUM'
        else:
            recommendation = 'SKIP'
            confidence = 'HIGH' if probability < 0.40 else 'LOW'

        return {
            'recommendation': recommendation,
            'win_probability': round(probability * 100, 1),
            'confidence': confidence,
            'direction': 'LONG',
        }


def main():
    parser = argparse.ArgumentParser(description='Train LONG ENTRY model')
    parser.add_argument('--strategy', type=str, default='momentum',
                        help='Strategy: momentum or pullback')
    parser.add_argument('--train', action='store_true', help='Train the model')
    args = parser.parse_args()

    if args.train:
        print("=" * 60)
        print("  LONG ENTRY MODEL TRAINING")
        print("=" * 60)

        model = EntryModel(args.strategy)
        model.train()
        model.get_feature_importance()
        model.save()
    else:
        print("LONG Entry Model")
        print("\nUsage:")
        print("  python -m analysis.entry_model --train")
        print("\nFeatures used:")
        for f in PRE_ENTRY_FEATURES_NUMERIC[:5]:
            print(f"  - {f}")
        print("  ...")


if __name__ == '__main__':
    main()
