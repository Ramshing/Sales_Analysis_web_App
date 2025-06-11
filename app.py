from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import logging
import os

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": os.getenv('ALLOWED_ORIGINS', '*')}})  # Enable CORS for cross-origin requests from the frontend

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/api/analyze', methods=['POST'])
def analyze_file():
    try:
        logger.info("Received /api/analyze request")
        # Validate request
        if 'file' not in request.files:
            logger.error("No file part in request")
            return jsonify({'error': 'No file part in request'}), 400
        file = request.files['file']
        if file.filename == '':
            logger.error("No file selected")
            return jsonify({'error': 'No file selected'}), 400
        if not file.filename.endswith(('.xlsx', '.xls')):
            logger.error(f"Invalid file format: {file.filename}")
            return jsonify({'error': 'Invalid file format. Please upload an Excel file (.xlsx or .xls)'}), 400

        # Get form parameters
        specific_months = request.form.get('specificMonths', 'Jan')  # e.g., 'Jan,Feb,Mar'
        product_filter = request.form.get('productFilter', 'all')
        logger.info(f"Received parameters: specificMonths={specific_months}, productFilter={product_filter}")

        # Read Excel file
        logger.info(f"Reading file: {file.filename}")
        df = pd.read_excel(file, engine='openpyxl')
        logger.info(f"Excel columns: {list(df.columns)}")

        # Validate required columns
        required_columns = ['Date', 'Sales', 'Revenue', 'Product']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.error(f"Missing columns: {missing_columns}")
            return jsonify({'error': f'Missing required columns: {", ".join(missing_columns)}'}), 400

        # Validate data types
        if not pd.api.types.is_numeric_dtype(df['Sales']) or not pd.api.types.is_numeric_dtype(df['Revenue']):
            logger.error("Sales or Revenue contains non-numeric values")
            return jsonify({'error': 'Sales and Revenue columns must contain numeric values'}), 400

        # Process Date column
        try:
            df['Date'] = pd.to_datetime(df['Date'])
        except ValueError as e:
            logger.error(f"Invalid date format in Date column: {str(e)}")
            return jsonify({'error': f'Invalid date format in Date column: {str(e)}'}), 400

        # Filter by specific months
        if specific_months:
            month_list = [m.strip() for m in specific_months.split(',')]
            try:
                # Extract month names from Date column
                recent_data = df[df['Date'].dt.strftime('%b').isin(month_list)]
                if recent_data.empty:
                    logger.error(f"No data found for specified months: {specific_months}")
                    return jsonify({'error': f'No data found for specified months: {specific_months}'}), 400
            except Exception as e:
                logger.error(f"Invalid month names: {str(e)}")
                return jsonify({'error': f'Invalid month names provided: {str(e)}'}), 400
        else:
            # Default to all data if no specific months provided
            recent_data = df.copy()

        # # Filter by product
        # if product_filter != 'all':
        #     if product_filter not in recent_data['Product'].values:
        #         logger.error(f"Product filter '{product_filter}' not found")
        #         return jsonify({'error': f'Product filter "{product_filter}" not found in data'}), 400
        #     recent_data = recent_data[recent_data['Product'] == product_filter]

        # Check if data is empty after filtering
        if recent_data.empty:
            logger.error("No data available after filtering")
            return jsonify({'error': 'No data available after applying product filter'}), 400

        # Define a list of colors for the bar chart (hex codes that work for both light and dark themes)
        bar_colors = [
            '#3B82F6',  # Blue
            '#10B981',  # Green
            '#F59E0B',  # Yellow
            '#EF4444',  # Red
            '#8B5CF6',  # Purple
            '#EC4899',  # Pink
            '#06B6D4',  # Cyan
            '#D97706',  # Amber
            '#6366F1',  # Indigo
            '#F472B6',  # Rose
            '#14B8A6',  # Teal
            '#F43F5E'  # Rose Red
        ]

        # Generate bar chart data (Date and Sales)
        bar_chart_data = (
            recent_data.groupby(recent_data['Date'].dt.strftime('%b'))
            .agg({'Sales': 'sum'})
            .reset_index()
            .rename(columns={'Date': 'month','Sales': 'sales'})
            #.to_dict('records')
        )
        # Add a color column by mapping months to colors
        # Use modulo to cycle through colors if there are more months than colors
        bar_chart_data['color'] = [
            bar_colors[i % len(bar_colors)] for i in range(len(bar_chart_data))
        ]

        # Convert to dictionary format for JSON response
        bar_chart_data = bar_chart_data.to_dict('records')

        # Generate pie chart data (Product and Sales)
        pie_chart_data = (
            recent_data.groupby('Product')['Sales']
            .sum()
            .reset_index()
            .sort_values('Sales', ascending=False)
            .head(5)
        )
        colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6']
        total_sales = recent_data['Sales'].sum()
        pie_chart_data = [
            {
                'name': row['Product'],
                'value': round(row['Sales'] / total_sales * 100, 1) if total_sales > 0 else 0,
                'color': colors[i % len(colors)]
            }
            for i, row in pie_chart_data.iterrows()
        ]

        # Generate summary stats
        total_revenue = recent_data['Revenue'].sum()
        total_sales_sum = recent_data['Sales'].sum()
        avg_sales = total_sales_sum / recent_data['Sales'].count() if recent_data['Sales'].count() > 0 else 0
        summary_stats = [
            {
                'label': 'Total Revenue',
                'value': f"${total_revenue:,.2f}",
                'trend': 'neutral'
            },
            {
                'label': 'Total Sales',
                'value': f"{total_sales_sum:,.0f}",
                'trend': 'neutral'
            },
            {
                'label': 'Average Sales',
                'value': f"{avg_sales:,.2f}",
                'trend': 'neutral'
            },
        ]

        # Generate insights
        top_month = recent_data.groupby(recent_data['Date'].dt.strftime('%b'))[
            'Sales'].sum().idxmax() if not recent_data.empty else "N/A"
        top_product = recent_data.groupby('Product')['Sales'].sum().idxmax() if not recent_data.empty else "N/A"
        insights = {
            'topPerformers': [
                f"{top_month} showed the highest sales volume" if top_month != "N/A" else "No data available",
                f"{top_product} dominates with {pie_chart_data[0]['value']}% market share" if pie_chart_data else "No data available",
                "Review sales trends for optimization",
            ],
            'recommendations': [
                f"Focus marketing efforts on {top_product} success" if top_product != "N/A" else "No top product identified",
                "Analyze underperforming products",
                f"Consider expanding successful {top_month} strategies" if top_month != "N/A" else "No top month identified",
            ]
        }

        logger.info("Analysis completed successfully")
        return jsonify({
            'barChartData': bar_chart_data,
            'pieChartData': pie_chart_data,
            'summaryStats': summary_stats,
            'insights': insights
        })

    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        return jsonify({'error': f'Failed to process file: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)