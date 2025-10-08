import pandas as pd

df = pd.read_csv('output.csv')
print(f"Total rows in output.csv: {len(df)}")

df['coord_key'] = df['sumo_x'].round(2).astype(str) + '_' + df['sumo_y'].round(2).astype(str)
duplicates = df[df.duplicated(subset=['coord_key'], keep=False)]
print(f"Rows with duplicate coordinates: {len(duplicates)}")
print(f"Unique coordinate pairs: {df['coord_key'].nunique()}")

if len(duplicates) > 0:
    print("\nExample duplicate coordinates:")
    sample_coord = duplicates['coord_key'].iloc[0]
    sample_dups = df[df['coord_key'] == sample_coord]
    print(sample_dups[['id', 'sumo_x', 'sumo_y']].head())

df_dedup = df.drop_duplicates(subset=['coord_key'], keep='first')
print(f"\nAfter removing duplicates: {len(df_dedup)} unique locations")

df_dedup = df_dedup.drop('coord_key', axis=1)  
df_dedup.to_csv('output_dedup.csv', index=False)
print(f"Saved to output_dedup.csv")

df_dedup['id'] = range(len(df_dedup))
df_dedup.to_csv('output_dedup_reindexed.csv', index=False)
print(f"Saved with new sequential IDs to output_dedup_reindexed.csv")
