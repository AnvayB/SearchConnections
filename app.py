from flask import Flask, render_template, request, jsonify
import pandas as pd
import os

app = Flask(__name__)

# Load the data
def load_data():
    anvay = pd.read_csv('./files/anvay-connections.csv')
    anil = pd.read_csv('./files/anil-connections.csv')
    bilwa = pd.read_csv('./files/bilwa-connections.csv')
    
    return anvay, anil, bilwa

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search')
def search():
    company_name = request.args.get('company', '').strip()
    
    if not company_name:
        return jsonify({'error': 'Please provide a company name'})
    
    anvay, anil, bilwa = load_data()
    
    # Search in all datasets
    anvay_matches = anvay[anvay['Company'].str.lower() == company_name.lower()]
    anil_matches = anil[anil['Company'].str.lower() == company_name.lower()]
    bilwa_matches = bilwa[bilwa['Company'].str.lower() == company_name.lower()]
    
    # Filter anil matches for Closeness 1.0 or 2.0
    filtered_anil_matches = anil_matches[anil_matches['Closeness'].isin([1.0, 2.0])]
    
    # Convert to dictionaries for JSON response
    anvay_results = anvay_matches.to_dict('records') if len(anvay_matches) > 0 else []
    anil_results = filtered_anil_matches.to_dict('records') if len(filtered_anil_matches) > 0 else []
    bilwa_results = bilwa_matches.to_dict('records') if len(bilwa_matches) > 0 else []
    
    return jsonify({
        'company': company_name,
        'anvay_matches': anvay_results,
        'anil_matches': anil_results,
        'bilwa_matches': bilwa_results,
        'anvay_count': len(anvay_results),
        'anil_count': len(anil_results),
        'bilwa_count': len(bilwa_results)
    })

@app.route('/companies')
def get_companies():
    anvay, anil, bilwa = load_data()
    
    # Get unique companies from all datasets
    anvay_companies = set(anvay['Company'].dropna().unique())
    anil_companies = set(anil['Company'].dropna().unique())
    bilwa_companies = set(bilwa['Company'].dropna().unique())
    
    # Combine and sort
    all_companies = sorted(list(anvay_companies.union(anil_companies).union(bilwa_companies)))
    
    return jsonify({'companies': all_companies})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080) 