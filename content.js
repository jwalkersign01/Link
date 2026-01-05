(function () {
    let lastUrl = location.href;

    const logData = (type, data) => {
        console.log(`%c[LinkedIn Extractor] ${type} Detected:`, 'color: #0077b5; font-weight: bold;', data);

        // Send data to Flask backend
        fetch('http://192.168.100.135:3000/collect', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
            .then(response => response.json())
            .then(result => {
                console.log('%c[LinkedIn Extractor] Backend Response:', 'color: #28a745; font-weight: bold;', result);
            })
            .catch(error => {
                console.error('%c[LinkedIn Extractor] Backend Error:', 'color: #dc3545; font-weight: bold;', error);
            });
    };

    const extractPersonData = () => {
        // Robust selectors for late 2024 / early 2025
        const nameElement = document.querySelector('h1') ||
            document.querySelector('.text-heading-xlarge') ||
            document.querySelector('.pv-top-card-section__name');

        const name = nameElement ? nameElement.innerText.trim() : 'N/A';

        const nameParts = name.split(' ');
        const firstName = nameParts[0] || 'N/A';
        const lastName = nameParts.slice(1).join(' ') || 'N/A';

        // Headline / Job Title
        const headlineElement = document.querySelector('.text-body-medium.break-words') ||
            document.querySelector('.pv-text-details__left-panel-mt2 span');
        const jobTitle = headlineElement ? headlineElement.innerText.trim() : 'N/A';

        // Location
        const locationElement = document.querySelector('.text-body-small.inline.t-black--light.break-words') ||
            document.querySelector('.pv-text-details__left-panel-mt2 .text-body-small');
        const locationText = locationElement ? locationElement.innerText.trim() : 'N/A';

        // Company detection - looking for the current position in the top fold or experience section
        const companyElement = document.querySelector('.inline-show-more-text--is-collapsed') ||
            document.querySelector('[data-field="experience_company_name"]') ||
            document.querySelector('.pv-text-details__right-panel-item-text');

        const companyName = companyElement ? companyElement.innerText.trim() : 'N/A';

        // About section (Summary)
        const aboutElement = document.querySelector('#about')?.parentElement.querySelector('.inline-show-more-text') ||
            document.querySelector('.pv-about-section .inline-show-more-text');
        const aboutSummary = aboutElement ? aboutElement.innerText.trim() : 'N/A';

        const personData = {
            firstName,
            lastName,
            jobTitle,
            companyName,
            location: locationText,
            aboutSummary: aboutSummary.substring(0, 200) + (aboutSummary.length > 200 ? '...' : ''),
            email: 'Check Contact Info Section (Usually hidden)',
            url: window.location.href,
            timestamp: new Date().toISOString()
        };

        logData('Person Profile', personData);
    };

    const extractCompanyData = () => {
        const nameElement = document.querySelector('h1') ||
            document.querySelector('.org-top-card-summary__title');
        const companyName = nameElement ? nameElement.innerText.trim() : 'N/A';

        // Robust domain extraction (Top Card + About Section)
        let domain = 'N/A';
        const domainSelectors = [
            '[data-field="website"] a',
            '.org-top-card-primary-actions__inner a',
            'a[data-control-name="topcard_website"]',
            '.org-about-company-module__company-page-url a',
            '.link-without-visited-state',
            'dd > a.link-without-visited-state'
        ];

        for (let selector of domainSelectors) {
            const el = document.querySelector(selector);
            if (el) {
                const href = el.href;
                if (href && !href.startsWith('javascript:')) {
                    domain = href;
                    break;
                } else if (el.innerText.trim().startsWith('http')) {
                    domain = el.innerText.trim();
                    break;
                }
            }
        }

        // Fallback: smart scan for external links
        if (domain === 'N/A' || domain.includes('javascript:') || (domain.includes('linkedin.com') && !domain.includes('redir/redirect'))) {
            const allLinks = document.querySelectorAll('.org-top-card a, .org-grid__content-main a, .org-about-module__margin-bottom a');
            for (let link of allLinks) {
                const href = link.href;
                if (href && !href.includes('linkedin.com') && !href.startsWith('javascript:') && (href.startsWith('http') || href.startsWith('www'))) {
                    domain = href;
                    break;
                }
            }
        }

        // Cleanup Domain
        if (domain.startsWith('http') || domain.startsWith('www')) {
            if (domain.includes('linkedin.com/redir/redirect')) {
                try {
                    const urlObj = new URL(domain);
                    domain = urlObj.searchParams.get('url') || domain;
                } catch (e) { }
            }
        } else {
            domain = 'N/A';
        }

        // Improved Info extraction (Employee Size, Industry, HQ)
        // Check both Top Card items and the About section definition list
        const infoItems = document.querySelectorAll('.org-top-card-summary-info-list__info-item') ||
            document.querySelectorAll('.t-14.t-black--light.mb1');

        let employeeSizeText = 'N/A';
        let industryString = 'N/A';
        let hqLocation = 'N/A';

        // Strategy A: Scan top card items
        infoItems.forEach((item, index) => {
            const text = item.innerText.trim();
            if (text.toLowerCase().includes('employees') || text.match(/\d+,\d+ \+ employees/) || text.match(/\d+-\d+/)) {
                employeeSizeText = text.split(' ')[0]; // Just the range/number
            } else if (index === 0 && !text.includes('followers')) {
                industryString = text;
            } else if (text.includes('·') || (index > 0 && !text.includes('employees') && !text.includes('followers'))) {
                hqLocation = text.split('·').pop().trim();
            }
        });

        // Strategy B: Scan About Section (dt/dd structure)
        const dts = document.querySelectorAll('dt');
        dts.forEach(dt => {
            const headerText = dt.innerText.trim().toLowerCase();
            const dd = dt.nextElementSibling;
            if (dd && dd.tagName === 'DD') {
                const val = dd.innerText.trim();
                if (headerText.includes('industry')) industryString = val;
                if (headerText.includes('company size')) {
                    // "1,001-5,000 employees" -> "1,001-5,000"
                    employeeSizeText = val.split(' employees')[0].split('\n')[0].trim();
                }
                if (headerText.includes('headquarters')) hqLocation = val;
                if (headerText.includes('website') && domain === 'N/A') {
                    const link = dd.querySelector('a');
                    if (link) domain = link.href;
                }
            }
        });

        // Strategy C: Specific data-field selectors
        const indEl = document.querySelector('[data-field="industry"]');
        if (indEl && industryString === 'N/A') industryString = indEl.innerText.trim();
        const sizeEl = document.querySelector('[data-field="company_size"]');
        if (sizeEl && employeeSizeText === 'N/A') employeeSizeText = sizeEl.innerText.trim().split(' employees')[0];

        const companyData = {
            companyName,
            industry: industryString,
            domain,
            employeeSize: employeeSizeText,
            headquarters: hqLocation,
            url: window.location.href,
            timestamp: new Date().toISOString()
        };

        logData('Company Profile', companyData);
    };

    const detectProfile = () => {
        const url = location.href;
        if (url.includes('/in/')) {
            console.log("[LinkedIn Extractor] Checking Person Profile...");
            setTimeout(extractPersonData, 3000); // Increased timeout for heavy LinkedIn pages
        } else if (url.includes('/company/')) {
            console.log("[LinkedIn Extractor] Checking Company Profile...");
            setTimeout(extractCompanyData, 3000);
        }
    };

    // Initial detection
    detectProfile();

    // Observe URL changes (SPA support)
    const observer = new MutationObserver(() => {
        if (location.href !== lastUrl) {
            lastUrl = location.href;
            detectProfile();
        }
    });
    observer.observe(document, { subtree: true, childList: true });

    // Add a floating button for debugging (In case auto-detection fails or user wants to manual trigger)
    const addDebugButton = () => {
        if (document.getElementById('linkedin-extractor-debug')) return;
        const btn = document.createElement('button');
        btn.id = 'linkedin-extractor-debug';
        btn.innerText = 'Scrape Profile Data';
        btn.style.cssText = `
            position: fixed !important;
            bottom: 20px !important;
            right: 20px !important;
            z-index: 2147483647 !important;
            background-color: #0077b5 !important;
            color: white !important;
            border: 2px solid white !important;
            padding: 12px 20px !important;
            border-radius: 30px !important;
            cursor: pointer !important;
            font-weight: bold !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3) !important;
            pointer-events: auto !important;
            font-family: inherit !important;
            display: block !important;
        `;
        btn.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log("[LinkedIn Extractor] Manual Scrape Triggered");
            detectProfile();
        };
        document.body.appendChild(btn);
    };

    // Re-check for button every few seconds since body might re-render
    setInterval(addDebugButton, 5000);

})();
