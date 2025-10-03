#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const minimist = require('minimist');

function calculateOptimalScaling(originalWidth, originalHeight, highResMode) {
  const aspectRatio = 4 / 5;
  const standardWidth = 1080;
  const standardHeight = Math.round(standardWidth / aspectRatio);
  const minSlices = 2;

  let sliceWidth = standardWidth;
  let sliceHeight = standardHeight;

  if (highResMode) {
    sliceHeight = originalHeight;
    sliceWidth = Math.round(sliceHeight * aspectRatio);
  }

  const scaleFactor = sliceHeight / originalHeight;
  const baseScaledWidth = Math.round(originalWidth * scaleFactor);
  const fullSlices = Math.floor(baseScaledWidth / sliceWidth);
  const remainingWidth = baseScaledWidth - (fullSlices * sliceWidth);

  let finalSliceCount;
  let finalScaledWidth;
  let finalScaledHeight;

  if (fullSlices < minSlices) {
    finalSliceCount = minSlices;
    finalScaledWidth = minSlices * sliceWidth;
    const adjustedScaleFactor = finalScaledWidth / originalWidth;
    finalScaledHeight = Math.round(originalHeight * adjustedScaleFactor);
  } else if (remainingWidth > (sliceWidth / 2)) {
    finalSliceCount = fullSlices + 1;
    finalScaledWidth = finalSliceCount * sliceWidth;
    const adjustedScaleFactor = finalScaledWidth / originalWidth;
    finalScaledHeight = Math.round(originalHeight * adjustedScaleFactor);
  } else {
    finalSliceCount = fullSlices;
    finalScaledWidth = finalSliceCount * sliceWidth;
    finalScaledHeight = sliceHeight;
  }

  return {
    sliceWidth,
    sliceHeight,
    sliceCount: finalSliceCount,
    scaledWidth: finalScaledWidth,
    scaledHeight: finalScaledHeight
  };
}

async function createFullViewImage({ inputPath, outputPath, originalWidth, originalHeight, sliceWidth, sliceHeight }) {
  const margin = Math.round(sliceWidth * 0.08);
  const availableWidth = sliceWidth - margin * 2;
  const availableHeight = sliceHeight - margin * 2;
  const originalAspect = originalWidth / originalHeight;

  let panoWidth;
  let panoHeight;

  if (originalAspect > availableWidth / availableHeight) {
    panoWidth = availableWidth;
    panoHeight = panoWidth / originalAspect;
  } else {
    panoHeight = availableHeight;
    panoWidth = panoHeight * originalAspect;
  }

  panoWidth = Math.max(1, Math.round(panoWidth));
  panoHeight = Math.max(1, Math.round(panoHeight));

  const x = Math.max(0, Math.round((sliceWidth - panoWidth) / 2));
  const y = Math.max(0, Math.round((sliceHeight - panoHeight) / 2));

  const panoramaBuffer = await sharp(inputPath)
    .resize({
      width: panoWidth,
      height: panoHeight,
      fit: 'inside'
    })
    .jpeg({ quality: 95 })
    .toBuffer();

  const background = sharp({
    create: {
      width: sliceWidth,
      height: sliceHeight,
      channels: 3,
      background: '#ffffff'
    }
  });

  const canvas = background.composite([
    {
      input: panoramaBuffer,
      top: y,
      left: x
    }
  ]);

  // Add subtle border similar to the web app implementation
  const borderWidth = 1;
  const borderColor = { r: 238, g: 238, b: 238, alpha: 1 };
  const borderOverlay = {
    create: {
      width: sliceWidth,
      height: sliceHeight,
      channels: 4,
      background: { r: 0, g: 0, b: 0, alpha: 0 }
    }
  };

  const overlay = await sharp(borderOverlay)
    .composite([
      {
        input: {
          create: {
            width: sliceWidth - borderWidth * 2,
            height: sliceHeight - borderWidth * 2,
            channels: 4,
            background: borderColor
          }
        },
        top: borderWidth,
        left: borderWidth,
        blend: 'dest-out'
      }
    ])
    .png()
    .toBuffer();

  const result = await canvas
    .composite([
      {
        input: overlay,
        blend: 'over'
      }
    ])
    .jpeg({ quality: 95 })
    .toBuffer();

  await sharp(result).toFile(outputPath);
}

async function run() {
  const args = minimist(process.argv.slice(2), {
    boolean: ['highRes'],
    alias: { i: 'input', o: 'output', m: 'mode' },
    default: { mode: 'standard' }
  });

  const inputPath = args.input ? path.resolve(args.input) : null;
  const outputDir = args.output ? path.resolve(args.output) : null;
  const modeFlag = (args.mode || '').toLowerCase();
  const mode = args.highRes || modeFlag === 'highres' ? 'highres' : 'standard';

  if (!inputPath || !outputDir) {
    console.error(JSON.stringify({ error: 'Both --input and --output are required.' }));
    process.exit(1);
  }

  if (!fs.existsSync(inputPath)) {
    console.error(JSON.stringify({ error: `Input file not found: ${inputPath}` }));
    process.exit(1);
  }

  await fs.promises.mkdir(outputDir, { recursive: true });

  try {
    const metadata = await sharp(inputPath).metadata();
    const { width: originalWidth, height: originalHeight } = metadata;

    if (!originalWidth || !originalHeight) {
      throw new Error('Unable to determine image dimensions');
    }

    const scaling = calculateOptimalScaling(originalWidth, originalHeight, mode === 'highres');
    const resizedBuffer = await sharp(inputPath)
      .resize({
        width: scaling.scaledWidth,
        height: scaling.scaledHeight,
        fit: 'fill'
      })
      .jpeg({ quality: 95 })
      .toBuffer();

    const slices = [];
    for (let index = 0; index < scaling.sliceCount; index += 1) {
      const left = index * scaling.sliceWidth;
      const width = Math.min(scaling.sliceWidth, scaling.scaledWidth - left);

      const slicePath = path.join(outputDir, `slice-${String(index + 1).padStart(2, '0')}.jpg`);

      await sharp(resizedBuffer)
        .extract({
          left,
          top: 0,
          width,
          height: scaling.scaledHeight
        })
        .resize({
          width: scaling.sliceWidth,
          height: scaling.sliceHeight,
          fit: 'fill'
        })
        .jpeg({ quality: 95 })
        .toFile(slicePath);

      slices.push({
        filename: path.basename(slicePath),
        width: scaling.sliceWidth,
        height: scaling.sliceHeight
      });
    }

    const fullViewName = 'full-view.jpg';
    const fullViewPath = path.join(outputDir, fullViewName);
    await createFullViewImage({
      inputPath,
      outputPath: fullViewPath,
      originalWidth,
      originalHeight,
      sliceWidth: scaling.sliceWidth,
      sliceHeight: scaling.sliceHeight
    });

    const response = {
      mode,
      sliceCount: scaling.sliceCount,
      sliceWidth: scaling.sliceWidth,
      sliceHeight: scaling.sliceHeight,
      scaledWidth: scaling.scaledWidth,
      scaledHeight: scaling.scaledHeight,
      slices,
      fullView: {
        filename: fullViewName,
        width: scaling.sliceWidth,
        height: scaling.sliceHeight
      }
    };

    console.log(JSON.stringify(response));
  } catch (error) {
    console.error(JSON.stringify({ error: error.message }));
    process.exit(1);
  }
}

run();
