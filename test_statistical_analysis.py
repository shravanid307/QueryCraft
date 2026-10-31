from agents.statistical_analysis import calculate_correlation


result = calculate_correlation(
    table="wineqt",
    column_x="alcohol",
    column_y="quality",
    db_path="data/uploaded_databases/WineQT.db",
    method="pearson",
)

print("\nCorrelation Analysis Result:")
for key, value in result.items():
    print(f"{key}: {value}")