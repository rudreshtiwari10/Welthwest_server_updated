import pandas as pd

def normalize_data(data_frame, base_column='Close'):
    """
    Normalize data to percentage change from first value
    
    Parameters:
    data_frame (DataFrame): Data to normalize
    base_column (str): Column to use for normalization
    
    Returns:
    DataFrame: Normalized data
    """
    if base_column not in data_frame.columns:
        return data_frame
        
    normalized = data_frame.copy()
    normalized[f'Normalized_{base_column}'] = data_frame[base_column] / data_frame[base_column].iloc[0] * 100
    return normalized

def calculate_statistics(data_frame):
    """
    Calculate basic statistics for a DataFrame
    
    Parameters:
    data_frame (DataFrame): Data to analyze
    
    Returns:
    dict: Statistics including min, max, mean, etc.
    """
    if len(data_frame) == 0:
        return {}
        
    stats = {}
    numeric_columns = data_frame.select_dtypes(include=['number']).columns
    
    for column in numeric_columns:
        stats[column] = {
            'min': float(data_frame[column].min()),
            'max': float(data_frame[column].max()),
            'mean': float(data_frame[column].mean()),
            'median': float(data_frame[column].median()),
            'std': float(data_frame[column].std())
        }
    
    return stats 