import pdfkit

# Without output_path, PDF is returned for assigning to a variable
pdf = pdfkit.from_url('http://google.com')