#!/bin/bash -e
#
# Populate files needed under 'cache' directory, by downloading
# four files from a dedicated resource set up for this purpose.
#

FILES="CURRENCY_USD.json DIVIDENDS_CSCO.json FUNDAMENTALS_CSCO.json STOCK_CSCO.json"

if ! test -e TAX.md; then
    echo "Error: Run from within ESPP2 directory" 1>&2
    exit 1
fi

# Check if a vault-key is available, to warn those who have it
VAULT=0
if test -e espp2/vault.json; then
    VAULT=1
fi

if test -n "$ESPP2_VAULT_PATH"; then
    VAULT=1
fi

if [ $VAULT = 1 ]; then
    echo "WARNING: You seem to have a vault.json file, maybe you'd like to"
    echo "         use the proper online resources instead of this tool?"
    echo
    echo -n "Type YES to continue: "
    read answer junk
    case "$answer" in
	Y*|y*)
            # OK, keep going - make a backup of 'cache'
	    test -d cache && rm -rf cache.backup && mv cache cache.backup
	    ;;

	*)
	    # Nope, exit out
	    echo "Some other time!"
	    exit 0
    esac
fi

# Establish the 'cache' directory without the files we need, and go there
mkdir -p cache
cd cache

rm -f $FILES

echo
echo "Please specify the URL-base exactly as provided by the Tax-force team,"
echo "to establish stock-prices and exchange rates needed under 'cache' dir."
echo
echo -n "URL-base: "

read url junk

for file in $FILES; do curl $url/$file -o $file; done

echo "Done"
