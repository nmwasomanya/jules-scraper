import http.server
import socketserver
import threading
import time
import random
import urllib.parse

PORT = 8000

def encode_cloudflare_email(email):
    """Encodes an email address using Cloudflare's method."""
    r = random.randint(0, 255)
    encoded = '{:02x}'.format(r)
    for char in email:
        encoded += '{:02x}'.format(ord(char) ^ r)
    return encoded

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
                <a href="/obfuscated">Obfuscated Emails</a>
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
        elif self.path == '/obfuscated':
            cf_email = encode_cloudflare_email('cloudflare@localtest.com')
            encoded_mailto = urllib.parse.quote('encoded@localtest.com')
            html = f"""
            <html>
            <body>
                <h1>Obfuscated Emails</h1>
                <p>Here are some tricky ones:</p>

                <!-- Text Obfuscation -->
                <p>Support: support [at] localtest [dot] com</p>
                <p>Sales: sales (at) localtest . com</p>
                <p>Info: info at localtest dot com</p>

                <!-- Cloudflare Style -->
                <p>Protected: <span class="__cf_email__" data-cfemail="{cf_email}">[email protected]</span></p>

                <!-- Encoded Mailto -->
                <a href="mailto:{encoded_mailto}">Email Encoded</a>
            </body>
            </html>
            """
        else:
            html = "<html><body>404 Not Found</body></html>"

        self.wfile.write(html.encode('utf-8'))

def start_server():
    # Allow address reuse
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), TestHandler) as httpd:
        print("serving at port", PORT)
        httpd.serve_forever()

if __name__ == "__main__":
    start_server()
