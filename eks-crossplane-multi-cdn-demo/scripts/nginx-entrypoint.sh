#!/bin/sh
# entrypoint.sh: Replace ${HOSTNAME} in HTML with the actual pod/container hostname and start nginx

set -e

# Substitute ${HOSTNAME} in the HTML file
if [ -f /usr/share/nginx/html/crossplane-sr-leadership_mgmt-demo_v2.html ]; then
  envsubst '${HOSTNAME}' < /usr/share/nginx/html/crossplane-sr-leadership_mgmt-demo_v2.html > /usr/share/nginx/html/crossplane-sr-leadership_mgmt-demo_v2.html.tmp
  mv /usr/share/nginx/html/crossplane-sr-leadership_mgmt-demo_v2.html.tmp /usr/share/nginx/html/crossplane-sr-leadership_mgmt-demo_v2.html
fi

exec nginx -g 'daemon off;'
