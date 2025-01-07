name: Download Images

on:
  workflow_dispatch:
    inputs:
      start_range:
        description: "Start range (optional)"
        required: false
        type: string
      end_range:
        description: "End range (optional)"
        required: false
        type: string
  schedule:
    # Run at 3AM Vietnam time (UTC+7) on 1st, 8th, 15th, and 22nd of each month
    - cron: "0 20 1,8,15,22 * *"  # 20:00 UTC = 03:00 UTC+7 next day

jobs:
  prepare-matrix:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.set-matrix.outputs.matrix }}
      total_end: ${{ steps.set-matrix.outputs.total_end }}
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.PAT }}

      - name: Load state and prepare matrix
        id: set-matrix
        run: |
          if [ -f range.json ]; then
            start=$(jq -r '.start' range.json)
            end=$(jq -r '.end' range.json)
          else
            start="${{ inputs.start_range || '1000' }}"
            end="${{ inputs.end_range || '2000' }}"
          fi
          
          # Create ranges for each letter a-z
          ranges=()
          for letter in {a..z}; do
            ranges+=("{\"prefix\":\"$letter\",\"start\":$start,\"end\":$end}")
          done
          
          matrix=$(printf '%s\n' "${ranges[@]}" | jq -sc '{range: .}')
          echo "matrix=$matrix" >> $GITHUB_OUTPUT
          echo "total_end=$end" >> $GITHUB_OUTPUT

  download-batch:
    needs: prepare-matrix
    runs-on: ubuntu-latest
    outputs:
      has_images: ${{ steps.check-downloads.outputs.has_images }}
    strategy:
      matrix: ${{fromJson(needs.prepare-matrix.outputs.matrix)}}
      fail-fast: false
      max-parallel: 4
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.PAT }}

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.x"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests Pillow

      - name: Process batch
        id: check-downloads
        run: |
          today=$(date +%Y%m%d)
          folder="images_${{ matrix.range.prefix }}_${today}_${{ matrix.range.start }}_to_${{ matrix.range.end }}"
          mkdir -p "$folder"
          
          echo "Processing batch: ${{ matrix.range.prefix }}${{ matrix.range.start }} to ${{ matrix.range.prefix }}${{ matrix.range.end }}"
          python crawler_images.py ${{ matrix.range.prefix }} ${{ matrix.range.start }} ${{ matrix.range.end }}
          
          # Check if any images were downloaded
          image_count=$(find "$folder" -name "*.jpg" | wc -l)
          if [ "$image_count" -eq 0 ]; then
            echo "No images downloaded in this batch"
            echo "has_images=false" >> $GITHUB_OUTPUT
            
            # Log the empty range
            echo "$(date '+%Y-%m-%d %H:%M:%S') - No images found in range ${{ matrix.range.start }} to ${{ matrix.range.end }} with prefix ${{ matrix.range.prefix }}" >> empty_ranges.log
          else
            echo "has_images=true" >> $GITHUB_OUTPUT
          fi

      - name: Upload batch artifacts
        uses: actions/upload-artifact@v4
        with:
          name: batch-${{ matrix.range.prefix }}-${{ matrix.range.start }}-${{ matrix.range.end }}
          path: images_*
          retention-days: 1

  commit-changes:
    needs: [prepare-matrix, download-batch]
    runs-on: ubuntu-latest
    permissions:
      contents: write
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.PAT }}
          fetch-depth: 0

      - name: Download all artifacts
        uses: actions/download-artifact@v4
        with:
          path: ./downloads
          merge-multiple: true

      - name: Move artifacts to root
        run: |
          cp -r ./downloads/* ./
          rm -rf ./downloads

      - name: Commit and push changes
        run: |
          git config user.name "${{ github.repository_owner }}"
          git config user.email "${{ github.repository_owner }}@users.noreply.github.com"

          # Create empty_ranges.log if it doesn't exist
          touch empty_ranges.log
          
          # Add empty range log if no images were found
          if [ "${{ needs.download-batch.outputs.has_images }}" = "false" ]; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') - No images found in range ${{ matrix.range.start }} to ${{ matrix.range.end }} with prefix ${{ matrix.range.prefix }}" >> empty_ranges.log
          fi

          # Update range.json for next run
          next_start=$((${{ needs.prepare-matrix.outputs.total_end }} + 1))
          next_end=$((${{ needs.prepare-matrix.outputs.total_end }} + 501))
          echo "{\"start\": $next_start, \"end\": $next_end}" > range.json
          git add range.json

          # Add all downloaded images and empty ranges log
          git add images_* empty_ranges.log
          
          if git diff --staged --quiet; then
            echo "No changes to commit"
            exit 0
          fi
          
          today=$(date +%Y-%m-%d)
          if [ "${{ needs.download-batch.outputs.has_images }}" = "true" ]; then
            git commit -m "chore: download images for prefix ${{ matrix.range.prefix }} in ${today} from ids ${next_start} to ${next_end}"
          else
            git commit -m "log: no images found in range ${{ matrix.range.start }} to ${{ matrix.range.end }}"
          fi
          git push

  trigger-next-workflow:
    needs: [download-batch, commit-changes]
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Next Download Images Workflow
        env:
          WORKFLOW_FILE_NAME: "download-images.yml"
        run: |
          curl -X POST \
            -H "Accept: application/vnd.github.v3+json" \
            -H "Authorization: token ${{ secrets.PAT }}" \
            https://api.github.com/repos/${{ github.repository }}/actions/workflows/${{ env.WORKFLOW_FILE_NAME }}/dispatches \
            -d '{"ref":"main"}'
