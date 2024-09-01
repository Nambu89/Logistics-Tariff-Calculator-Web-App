# Logistics-Tariff-Calculator-Web-App

This web application is a Flask-based tool designed to calculate shipping costs for various types of products across different carriers in Spain. It provides a user-friendly interface for comparing shipping rates and determining the most cost-effective option for both regular shipments and returns.

## Features

- **Multi-Carrier Support:** Calculate and compare shipping costs across multiple carriers (CBL, ONTIME, MRW).
- **Product Type Flexibility:** Supports calculations for both `Normal` and `XS` products, with specific handling for pallets and smaller items.
- **Session Management:** Add multiple shipments to a session and calculate the total cost for all shipments at once.
- **Detailed Cost Breakdown:** Provides a detailed breakdown of shipping costs, including fuel surcharges, insurance, and other relevant fees.
- **Return Shipments:** Calculate the most cost-effective option for product returns.
- **Error Handling:** Includes robust error handling and logging for troubleshooting issues with data formats or missing columns.

## Prerequisites

Before you begin, ensure you have met the following requirements:

- Python 3.7+
- Flask
- pandas
- numpy
- Excel files with carrier rates and product information:
  - `Tarifas_CBL.xlsx`
  - `Tarifas_ONTIME.xlsx`
  - `Tarifas_MRW.xlsx`
  - `Productos.xlsx`

## Installation

1. Clone this repository:
   git clone https://github.com/Nambu89/Logistics-Tariff-Calculator-Web-App
2. Navigate to the project directory:
   cd Logistics-Tariff-Calculator-Web-App
3. Install the required packages:
   pip install -r requirements.txt
4. Place the necessary Excel files (Tarifas_CBL.xlsx, Tarifas_ONTIME.xlsx, Tarifas_MRW.xlsx, Productos.xlsx) in the root directory of the project.

## Usage
1. Run the Flask Application:
   python app.py
2. Open a web browser and navigate to http://localhost:5000.
3. Use the web interface to:
   * Select Product Type: Choose between Normal or XS products.
      * For Normal products, specify the Palet Type, Product Height, and Destination Province.
      * For XS products, specify the Category, SKU, Number of Packages, Delivery Mode, and Destination Province.
   * Add Shipments: Add the current shipment details to the session.
   * Calculate Total: Calculate the total cost of all shipments added to the session.
   * Reset Shipments: Clear all shipments in the session and start over.
  
## Contributing
Contributions to the Logistics Tariff Calculator Web App are welcome. Please follow these steps:
1. Fork the repository.Create a new branch: git checkout -b <branch_name>.
2. Make your changes and commit them: git commit -m '<commit_message>'.
3. Push to the original branch: git push origin <project_name>/<branch_name>.
4. Create the pull request.

Alternatively, see the GitHub documentation on creating a pull request.

## License
This project uses the following license: MIT License.

## Contact
If you want to contact me, you can reach me at fernandopradagorge@tutanota.com.

Acknowledgements
Flask
pandas
numpy
