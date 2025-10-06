import os
import re
from collections import Counter
import matplotlib.pyplot as plt

# Step 1: Gather all .md files from _posts and its subfolders
root_folder = '_posts'
md_files = []
for subdir, dirs, files in os.walk(root_folder):
    for file in files:
        if file.endswith('.md'):
            md_files.append(os.path.join(subdir, file))

# Step 2: Extract month (yy-mm) from filenames
months = []
for file in md_files:
    filename = os.path.basename(file)
    match = re.match(r'(\d{2}-\d{2}-\d{2})-', filename)
    if match:
        date_str = match.group(1)  # yy-mm-dd
        month_str = date_str[:5]   # yy-mm
        months.append(month_str)

# Step 3: Count posts per month
post_counts = Counter(months)

# Step 4: Calculate total and average posts
total_posts = sum(post_counts.values())
avg_posts_per_month = total_posts / len(post_counts) if post_counts else 0

# Step 5: Plot the bar chart
months_sorted = sorted(post_counts.keys())
counts_sorted = [post_counts[m] for m in months_sorted]

plt.figure(figsize=(10, 6))
plt.bar(months_sorted, counts_sorted, color='skyblue')
plt.xlabel('Month (yy-mm)')
plt.ylabel('Number of Posts')
plt.title('Number of Posts per Month')
plt.xticks(rotation=45)

# Display total and average on the plot
plt.figtext(0.15, 0.85, f'Total Posts: {total_posts}', fontsize=12, color='black')
plt.figtext(0.15, 0.80, f'Average Posts per Month: {avg_posts_per_month:.2f}', fontsize=12, color='black')

plt.tight_layout()
plt.show()
