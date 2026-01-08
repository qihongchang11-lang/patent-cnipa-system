#!/usr/bin/env node

const fs = require('fs').promises;
const path = require('path');
const PatentValidator = require('../src/checks/patent-validator');
const logger = require('../src/utils/logger');

async function validateApplication(filePath) {
    try {
        console.log(`Validating patent application: ${filePath}`);

        // Check if file exists
        try {
            await fs.access(filePath);
        } catch (error) {
            console.error(`File not found: ${filePath}`);
            process.exit(1);
        }

        // Load application data
        const content = await fs.readFile(filePath, 'utf8');
        const ext = path.extname(filePath).toLowerCase();

        let applicationData;
        switch (ext) {
            case '.json':
                applicationData = JSON.parse(content);
                break;
            case '.xml':
                applicationData = await parseXML(content);
                break;
            case '.yaml':
            case '.yml':
                const yaml = require('js-yaml');
                applicationData = yaml.load(content);
                break;
            default:
                console.error(`Unsupported file format: ${ext}`);
                process.exit(1);
        }

        // Validate application
        const validator = new PatentValidator();
        const result = await validator.validateApplication(applicationData);

        // Display results
        console.log('\n=== Validation Results ===');
        console.log(`Valid: ${result.valid}`);

        if (result.errors.length > 0) {
            console.log('\nErrors:');
            result.errors.forEach((error, index) => {
                console.log(`  ${index + 1}. ${error}`);
            });
        }

        if (result.warnings && result.warnings.length > 0) {
            console.log('\nWarnings:');
            result.warnings.forEach((warning, index) => {
                console.log(`  ${index + 1}. ${warning}`);
            });
        }

        if (result.recommendations && result.recommendations.length > 0) {
            console.log('\nRecommendations:');
            result.recommendations.forEach((recommendation, index) => {
                console.log(`  ${index + 1}. ${recommendation}`);
            });
        }

        // Generate detailed report if requested
        if (process.argv.includes('--detailed')) {
            await generateDetailedReport(filePath, result);
        }

        process.exit(result.valid ? 0 : 1);

    } catch (error) {
        console.error('Validation failed:', error.message);
        logger.error('Validation error:', error);
        process.exit(1);
    }
}

async function parseXML(content) {
    const xml2js = require('xml2js');
    const parser = new xml2js.Parser();

    return new Promise((resolve, reject) => {
        parser.parseString(content, (err, result) => {
            if (err) reject(err);
            else resolve(result);
        });
    });
}

async function generateDetailedReport(filePath, validationResult) {
    const report = {
        timestamp: new Date().toISOString(),
        file: filePath,
        validation: validationResult,
        summary: {
            totalErrors: validationResult.errors.length,
            totalWarnings: validationResult.warnings?.length || 0,
            totalRecommendations: validationResult.recommendations?.length || 0,
            status: validationResult.valid ? 'PASSED' : 'FAILED'
        }
    };

    const reportFile = `${filePath}.validation-report.json`;
    await fs.writeFile(reportFile, JSON.stringify(report, null, 2));

    console.log(`\nDetailed validation report saved to: ${reportFile}`);
}

// Main execution
if (require.main === module) {
    const filePath = process.argv[2];

    if (!filePath) {
        console.error('Usage: node validate-application.js <patent-application-file> [--detailed]');
        process.exit(1);
    }

    validateApplication(filePath);
}

module.exports = { validateApplication };