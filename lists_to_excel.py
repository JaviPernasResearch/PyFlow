import pandas as pd



# Data

priorities= [64, 19, 1, 2, 3, 27, 4, 5, 23, 6, 7, 8, 9, 10, 28, 11, 12, 13, 14, 15, 16, 17, 18, 20, 52, 89, 21, 22, 24, 25, 26, 29, 30, 31, 32, 33, 34, 43, 35, 36, 37, 38, 39, 40, 41, 42, 44, 45, 46, 47, 48, 61, 49, 50, 51, 53, 54, 55, 56, 57, 58, 59, 60, 62, 63, 65, 66, 67, 81, 78, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 79, 80, 82, 83, 84, 85, 86, 87, 88, 90]
inspections = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0]



# Create a DataFrame

df = pd.DataFrame({

    "Priorities": priorities,

    "Inspections": inspections

})


# Save DataFrame to an Excel file

file_path = "priorities_and_inspections.xlsx"

df.to_excel(file_path, index=False)



file_path