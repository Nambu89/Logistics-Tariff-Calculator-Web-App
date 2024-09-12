# Logistics-Tariff-Calculator-Web-App

This web application is a Flask-based tool designed to calculate shipping costs for various types of products across different carriers in Spain. It provides a user-friendly interface for comparing shipping rates and determining the most cost-effective option for both regular shipments and returns.

## Features

- **Multi-Carrier Support:** Calculate and compare shipping costs across multiple carriers (CBL, ONTIME, MRW).
- **Product Type Flexibility:** Supports calculations for both `Normal` and `XS` products, with specific handling for pallets and smaller items.
- **Bulk Order Processing:** Upload and process multiple orders at once using Excel files.
- **Intelligent Pallet Packing:** Automatically organizes products into pallets, considering weight and volume constraints.
- **Special Product Handling:** Custom logic for specific product types like COMBI and LAVADORA.
- **Detailed Cost Breakdown:** Provides a detailed breakdown of shipping costs, including fuel surcharges, insurance, and other relevant fees.
- **Return Shipments:** Calculate the most cost-effective option for product returns.
- **Comprehensive Order Analysis:** Generates detailed summaries of processed orders, including optimal carrier selection and cost comparisons.
- **Shipping Records Logging:** Automatically saves shipping details for each shipment processed in a CSV file for future analysis and potential AI model training.
- **Error Handling and Logging:** Includes robust error handling and logging for troubleshooting issues with data formats or missing information.

## Prerequisites

Before you begin, ensure you have met the following requirements:

- Python 3.7+
- Flask
- pandas
- numpy
- openpyxl
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
2. Open a web browser and navigate to `http://localhost:5000`.
3. Use the web interface to:
- Upload an Excel file containing order details.
- Select the destination province for the shipment.
- Process the order to get a detailed breakdown of shipping options and costs.
- Calculate return costs for specific products.

## New Features and Optimizations

- **Improved Order Processing:** Enhanced logic for handling various product types and packing them efficiently into pallets.
- **Detailed Order Analysis:** New functionality to provide comprehensive summaries of processed orders, including per-shipment breakdowns and overall cost comparisons.
- **CSV Logging:** Implementation of a system to log all processed shipments into a CSV file (`registros_envio.csv`) for record-keeping and potential future analysis.
- **Code Refactoring:** Improved code structure and readability, with better separation of concerns and more modular functions.
- **Enhanced Error Handling:** More robust error checking and informative error messages throughout the application.

## Logging Shipments for Future AI Training

The application now includes functionality to log each shipment processed. This feature allows the system to save key details of each shipment (such as SKU, quantity, weights, volumes, optimal carrier, etc.) in a CSV file (`registros_envio.csv`). This log will grow over time and can be used to train a machine learning model to predict optimal shipping configurations in the future, reducing the need for human input.

## Contributing

Contributions to the Logistics Tariff Calculator Web App are welcome. Please follow these steps:

1. Fork the repository.
2. Create a new branch: `git checkout -b <branch_name>`.
3. Make your changes and commit them: `git commit -m '<commit_message>'`.
4. Push to the original branch: `git push origin <project_name>/<branch_name>`.
5. Create the pull request.

Alternatively, see the GitHub documentation on creating a pull request.

## License

This project uses the following license: MIT License.

## Contact

If you want to contact me, you can reach me at fernandopradagorge@tutanota.com.

## Acknowledgements

- Flask
- pandas
- numpy
- openpyxl