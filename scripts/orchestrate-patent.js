#!/usr/bin/env node

const fs = require('fs').promises;
const path = require('path');
const CnipaPatentSystem = require('../src/orchestrator/index');
const logger = require('../src/utils/logger');

async function orchestratePatent(patentFile, options = {}) {
    try {
        console.log(`Starting patent orchestration for: ${patentFile}`);
        console.log(`Job Card: ${options.jobCard || 'default'}`);
        console.log(`Processing Mode: ${options.mode || 'full'}`);

        // Check if patent file exists
        try {
            await fs.access(patentFile);
        } catch (error) {
            console.error(`Patent file not found: ${patentFile}`);
            process.exit(1);
        }

        // Create patent system instance
        const system = new CnipaPatentSystem();

        await system.start();

        console.log('System initialized, processing application...');

        // Load and process the patent application
        const result = await system.processApplication(patentFile);

        // Display results
        console.log('\n=== Orchestration Results ===');
        console.log(`Status: ${result.status || 'completed'}`);
        console.log(`Processing Time: ${result.duration || 'N/A'}`);
        console.log(`Steps Completed: ${result.stepsCompleted || 0}`);
        console.log(`Steps Total: ${result.stepsTotal || 0}`);

        if (result.errors && result.errors.length > 0) {
            console.log(`\nErrors encountered:`);
            result.errors.forEach((error, index) => {
                console.log(`  ${index + 1}. ${error}`);
            });
        }

        if (result.warnings && result.warnings.length > 0) {
            console.log(`\nWarnings:`);
            result.warnings.forEach((warning, index) => {
                console.log(`  ${index + 1}. ${warning}`);
            });
        }

        if (result.outputFiles && result.outputFiles.length > 0) {
            console.log(`\nGenerated files:`);
            result.outputFiles.forEach((file, index) => {
                console.log(`  ${index + 1}. ${file}`);
            });
        }

        // Save results
        if (options.output) {
            await saveOrchestrationResult(options.output, result);
            console.log(`\nResults saved to: ${options.output}`);
        }

        // Stop the system
        await system.stop();

        console.log('\nPatent orchestration completed successfully');
        process.exit(0);

    } catch (error) {
        console.error('Patent orchestration failed:', error.message);
        logger.error('Orchestration error:', error);

        if (options.debug) {
            console.error('Full error stack:');
            console.error(error.stack);
        }

        process.exit(1);
    }
}

async function saveOrchestrationResult(outputFile, result) {
    const report = {
        timestamp: new Date().toISOString(),
        orchestration: result,
        metadata: {
            systemVersion: '1.0.0',
            schemaVersion: '1.0',
            format: 'cnipa-orchestration-v1'
        }
    };

    await fs.writeFile(outputFile, JSON.stringify(report, null, 2));
}

function parseArgs() {
    const args = process.argv.slice(2);
    const options = {
        output: null,
        jobCard: 'patent-application-processing',
        mode: 'full',
        debug: false,
        dryRun: false
    };

    for (let i = 0; i < args.length; i++) {
        const arg = args[i];

        if (arg.startsWith('--')) {
            const [flag, value] = arg.split('=');

            switch (flag) {
                case '--output':
                case '-o':
                    options.output = value || args[++i];
                    break;
                case '--job-card':
                case '-j':
                    options.jobCard = value || args[++i];
                    break;
                case '--mode':
                case '-m':
                    options.mode = value || args[++i];
                    break;
                case '--debug':
                case '-d':
                    options.debug = true;
                    break;
                case '--dry-run':
                    options.dryRun = true;
                    break;
                case '--help':
                case '-h':
                    showHelp();
                    process.exit(0);
            }
        } else if (!options.input) {
            options.input = arg;
        }
    }

    return options;
}

function showHelp() {
    console.log(`
CNIPA Patent Orchestration Tool

Usage: node orchestrate-patent.js <patent-file> [options]

Options:
  -o, --output <file>     Save results to file
  -j, --job-card <id>     Job card to use (default: patent-application-processing)
  -m, --mode <mode>       Processing mode: full, validation, examination (default: full)
  -d, --debug             Enable debug output
  --dry-run              Perform validation without actual processing
  -h, --help             Show this help message

Examples:
  node orchestrate-patent.js ./data/drafts/application-123.json
  node orchestrate-patent.js ./application.xml --job-card=patent-validation-checklist
  node orchestrate-patent.js ./patent.docx --output=results.json --debug
  node orchestrate-patent.js ./patent.pdf --mode=validation --dry-run
`);
}

// Main execution
if (require.main === module) {
    const options = parseArgs();

    if (!options.input) {
        console.error('Error: Patent file path is required');
        console.error('Run with --help for usage information');
        process.exit(1);
    }

    orchestratePatent(options.input, options);
}

module.exports = { orchestratePatent };