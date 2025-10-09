# LSTM Model Training Guide

## The Issue You're Seeing

The error `OSError: [WinError 10038]` occurs when:
- Server is interrupted during LSTM training
- Training takes 5-10 minutes and needs to complete uninterrupted
- This is NOT a critical error - it's just the server shutting down

## Solutions

### ✅ **Method 1: Standalone Training (RECOMMENDED)**

Train the model **without running the server** using the dedicated training script:

```bash
cd WelthWestServer2_aws
python train_lstm_standalone.py
```

**Benefits:**
- No server interruption
- Clean training process
- Better progress visibility
- Takes 5-10 minutes

**Custom training:**
```bash
# Syntax: python train_lstm_standalone.py [ticker] [period] [epochs] [batch_size]
python train_lstm_standalone.py RELIANCE.NS 2y 50 32
python train_lstm_standalone.py TCS.NS 1y 30 32
```

---

### ⚡ **Method 2: Quick Training (FASTER)**

For testing or when you need quick results:

```bash
python quick_train_lstm.py
```

**Configuration:**
- 20 epochs (instead of 50)
- 1 year data (instead of 2)
- Takes ~2-3 minutes
- Less accurate but faster

---

### 🌐 **Method 3: Train via API (Server Running)**

If you want to train via API endpoint:

1. **Start the server in one terminal:**
   ```bash
   python server.py
   ```

2. **In another terminal, call the API:**
   ```bash
   curl -X POST http://localhost:5000/api/lstm_model/train \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
     -d '{
       "ticker": "RELIANCE.NS",
       "period": "2y",
       "epochs": 50,
       "batch_size": 32
     }'
   ```

3. **Wait for completion** (don't stop the server!)

---

### 🔧 **Method 4: Adjust Training Parameters**

For even faster training, create a custom script:

```python
# custom_train.py
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

from lstm_model import lstm_service

# Minimal training - very fast but less accurate
result = lstm_service.train_model(
    ticker="RELIANCE.NS",
    period="6mo",      # 6 months data
    epochs=10,         # Only 10 epochs
    batch_size=64,     # Larger batch size
    retrain=True
)

print(f"Status: {result.get('status')}")
print(f"Validation Loss: {result.get('validation_loss', 0):.6f}")
```

Run: `python custom_train.py` (~1 minute)

---

## Training Time Estimates

| Configuration | Data Period | Epochs | Time | Accuracy |
|--------------|-------------|--------|------|----------|
| **Full** | 2 years | 50 | 8-10 min | Best |
| **Standard** | 2 years | 30 | 5-7 min | Good |
| **Quick** | 1 year | 20 | 2-3 min | Fair |
| **Minimal** | 6 months | 10 | 1-2 min | Basic |

---

## After Training

Once training is complete:

1. **Start the server:**
   ```bash
   python server.py
   ```

2. **Test LSTM predictions:**
   ```bash
   # Via curl
   curl http://localhost:5000/api/lstm_model/predict?ticker=RELIANCE.NS

   # Via browser
   http://localhost:5000/test_lstm_hmm_forecast.html
   ```

3. **Get combined forecast:**
   ```bash
   curl http://localhost:5000/api/ai_forecast/full_trade_forecast?ticker=RELIANCE.NS
   ```

---

## Troubleshooting

### "Server crashes during training"
- **Solution:** Use Method 1 (Standalone Training)
- Don't train via API endpoint if server is unstable

### "Training is too slow"
- **Solution:** Use Method 2 (Quick Training) or reduce epochs
- Consider using GPU for faster training

### "Out of memory"
- **Solution:** Reduce batch_size:
  ```python
  result = lstm_service.train_model(
      ticker="RELIANCE.NS",
      batch_size=16,  # Reduced from 32
      epochs=30
  )
  ```

### "Model not found error"
- **Solution:** Complete training first
- Check if `lstm_model/lstm_model.h5` exists

### TensorFlow warnings
- These are normal deprecation warnings
- They don't affect functionality
- To suppress: `os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'`

---

## Verification

After training, verify the model:

```bash
python -c "from lstm_model import lstm_service; info = lstm_service.get_model_info(); print('Trained:', info.get('is_trained', False))"
```

Should output: `Trained: True`

---

## Recommended Workflow

### For Testing:
```bash
# 1. Quick training
python quick_train_lstm.py

# 2. Start server
python server.py

# 3. Test in browser
# Open: http://localhost:5000/test_lstm_hmm_forecast.html
```

### For Production:
```bash
# 1. Full training (one time)
python train_lstm_standalone.py RELIANCE.NS 2y 50 32

# 2. Start server
python server.py

# 3. Use in production
```

### For Multiple Stocks:
```bash
# Train for each major stock
python train_lstm_standalone.py RELIANCE.NS 2y 50 32
python train_lstm_standalone.py TCS.NS 2y 50 32
python train_lstm_standalone.py INFY.NS 2y 50 32
```

**Note:** The same model can predict for all stocks after training on one.

---

## Next Steps

1. ✅ Choose a training method (recommend Method 1)
2. ✅ Run the training script
3. ✅ Wait for completion (don't interrupt!)
4. ✅ Start server
5. ✅ Test predictions
6. ✅ Enjoy AI-powered forecasts!

---

## Files Created

- `train_lstm_standalone.py` - Full standalone training
- `quick_train_lstm.py` - Fast training with reduced epochs
- This guide - `TRAINING_GUIDE.md`

**Happy Training! 🚀**
