import http.server
import socketserver
import threading
import time

PORT = 8000

class TestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        html = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Welcome to Test Page</h1>
            <p>Here are some emails:</p>
            <ul>
                <li>contact@localtest.com</li>
                <li>support@localtest.com</li>
                <li><a href="mailto:sales@localtest.com">Sales</a></li>
            </ul>
            <p>And some bad ones:</p>
            <ul>
                <li>admin@test.edu (should be skipped by email filter if it were a domain, but here it is content)</li>
                <li>privacy@localtest.com (should be skipped by prefix)</li>
            </ul>

            <p>Socials:</p>
            <a href="https://facebook.com/localtestpage">Facebook</a>
            <a href="https://twitter.com/localtestpage">Twitter</a>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

def start_server():
    with socketserver.TCPServer(("", PORT), TestHandler) as httpd:
        print("serving at port", PORT)
        httpd.serve_forever()

if __name__ == "__main__":
    start_server()
