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

        if self.path == '/':
            html = """
            <html>
            <head><title>Home Page</title></head>
            <body>
                <h1>Home Page</h1>
                <p>No emails here, but check our contact page.</p>
                <a href="/contact">Contact Us</a>
                <a href="/book">Book Now</a>
                <a href="/about-us">About Us</a>
            </body>
            </html>
            """
        elif self.path == '/contact':
            html = """
            <html>
            <body>
                <h1>Contact Page</h1>
                <p>Email us at: contact@localtest.com</p>
                <a href="https://facebook.com/localtestpage">Facebook</a>
            </body>
            </html>
            """
        elif self.path == '/book':
            html = """
            <html>
            <body>
                <h1>Booking</h1>
                <p>Book with us:</p>
                <a href="https://square.site/book/123/myshop">Book on Square</a>
                <a href="https://booksy.com/mybusiness">Book on Booksy</a>
            </body>
            </html>
            """
        elif self.path == '/about-us':
            html = """
            <html>
            <body>
                <h1>About</h1>
                <p>We are a team.</p>
                <a href="/team">Meet the Team</a>
            </body>
            </html>
            """
        elif self.path == '/team':
             html = """
            <html>
            <body>
                <h1>Team</h1>
                <p>team@localtest.com</p>
            </body>
            </html>
            """
        else:
            html = "<html><body>404 Not Found</body></html>"

        self.wfile.write(html.encode('utf-8'))

def start_server():
    with socketserver.TCPServer(("", PORT), TestHandler) as httpd:
        print("serving at port", PORT)
        httpd.serve_forever()

if __name__ == "__main__":
    start_server()
