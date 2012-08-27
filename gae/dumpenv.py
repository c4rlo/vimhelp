import sys, os

print "Content-type: text/html\n"

print "<html><body><table>"
for k, v in os.environ.iteritems():
    print "<tr><td>{}</td><td>{}</td></tr>".format(k, v)
print "</table></body></html>"
